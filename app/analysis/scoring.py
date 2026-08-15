"""
Phase 1 適正価格推定 & 裁定スコアリング

フロー:
  1. build_fair_price_model(): DAG informed OLS で適正価格モデルを構築
  2. compute_arbitrage_scores(): 残差から裁定スコアを計算
  3. save_scores(): estimated_price / divergence_rate を DB に書き戻す

裁定スコアの解釈:
  divergence_rate = (price - estimated_price) / estimated_price
  < 0 → 割安（市場が適正より安く設定）→ 裁定機会
  > 0 → 割高（市場が適正より高く設定）

=== log(price) モデルを採用する理由 ===
線形モデル（price ~ X）は年数や総階数が平均から離れた物件で
予測価格が0円近く・負になりうる。この場合 divergence_rate の
分母が極小になり、乖離率が数百〜数千%に爆発する（2026-08 実データで確認済み）。

log(price) ~ X にすると:
  - 予測価格は exp(...) で必ず正
  - 係数は「1単位増加で価格が何%変化するか」という乗法的効果として解釈できる
    （不動産のヘドニック価格モデルで標準的な定式化）
  - 外れ値（超高額・超築古物件）への頑健性が上がる
"""
import logging
import math

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.analysis.matching import load_analysis_data, FLOOR_PLAN_MAP

logger = logging.getLogger(__name__)


def build_fair_price_model(df: pd.DataFrame):
    """DAGに基づく適正価格モデルを構築する（log(price) を目的変数とする）。

    - np.log(liv_area) による両対数化で外挿エラーを防止
    - C(area_group) による町名レベル固定効果で立地交絡を制御
    """
    # area_group は load_analysis_data() 側で計算済み（matching.py の
    # estimate_station_distance_effect() と同じロジックを共用するため）
    required = [
        "price",
        "station_distance",
        "floor",
        "liv_area",
        "age",
        "total_floors",
        "area_group",
    ]
    df_model = df.dropna(subset=required).copy()
    df_model = df_model[
        (df_model["price"] > 0) & (df_model["liv_area"] > 0)
    ]

    df_model["log_price"] = np.log(df_model["price"])

    n = len(df_model)
    logger.info("fair price model: %d rooms", n)

    if n < 50:
        raise ValueError(
            f"モデル構築に必要なデータが不足しています（現在 {n} 件、50件以上必要）"
        )

    formula = (
        "log_price ~ station_distance + floor + np.log(liv_area) + age"
        " + total_floors + C(area_group) + C(floor_plan_cat) +"
        " C(building_type_cat)"
    )
    model = smf.ols(formula, data=df_model).fit()

    key_vars = [
        "station_distance",
        "floor",
        "np.log(liv_area)",
        "age",
        "total_floors",
    ]
    summary = {
        "n": n,
        "r2": round(model.rsquared, 3),
        "r2_adj": round(model.rsquared_adj, 3),
        "coefficients": {
            v: {
                "pct_effect": (
                    round(model.params[v], 2)
                    if "log" in v
                    else round((np.exp(model.params[v]) - 1) * 100, 2)
                ),
                "pval": round(model.pvalues[v], 4),
                "ci95_pct": [
                    (
                        round(model.conf_int().loc[v, 0], 2)
                        if "log" in v
                        else round(
                            (np.exp(model.conf_int().loc[v, 0]) - 1) * 100, 2
                        )
                    ),
                    (
                        round(model.conf_int().loc[v, 1], 2)
                        if "log" in v
                        else round(
                            (np.exp(model.conf_int().loc[v, 1]) - 1) * 100, 2
                        )
                    ),
                ],
            }
            for v in key_vars
            if v in model.params
        },
    }

    logger.info(
        "model: R²=%.3f R²adj=%.3f n=%d (log-price v4)",
        model.rsquared,
        model.rsquared_adj,
        n,
    )
    for v, s in summary["coefficients"].items():
        logger.info("  %s: %+.2f%% (p=%.3f)", v, s["pct_effect"], s["pval"])

    return model, df_model, summary

def compute_arbitrage_scores(df_model: pd.DataFrame, model) -> pd.DataFrame:
    """
    適正価格と裁定スコアを計算する。

    Args:
        df_model: build_fair_price_model() が返したデータ
        model: fitted OLS model

    Returns:
        room_id, price, estimated_price, divergence_rate を含む DataFrame
    """
    df_out = df_model.copy()
    # model は log_price を予測するので exp() で円に戻す
    df_out["estimated_price"] = np.exp(model.predict(df_out)).round().astype(int)
    df_out["divergence_rate"] = (
        (df_out["price"] - df_out["estimated_price"]) / df_out["estimated_price"]
    ).round(4)

    # 統計サマリー
    neg = df_out[df_out["divergence_rate"] < -0.05]
    pos = df_out[df_out["divergence_rate"] > 0.05]
    logger.info(
        "arbitrage: 割安(>5%%)=%d件 割高(>5%%)=%d件 / 全%d件",
        len(neg), len(pos), len(df_out)
    )

    return df_out[["room_id", "price", "estimated_price", "divergence_rate"]]


def save_scores(engine: Engine, scores: pd.DataFrame) -> int:
    """
    estimated_price と divergence_rate を rooms テーブルに書き戻す。

    Returns:
        更新した行数
    """
    updated = 0
    with engine.begin() as conn:
        for _, row in scores.iterrows():
            conn.execute(
                text("""
                    UPDATE rooms
                    SET estimated_price = :ep,
                        divergence_rate = :dr
                    WHERE id = :id
                """),
                {
                    "ep": int(row["estimated_price"]),
                    "dr": float(row["divergence_rate"]),
                    "id": int(row["room_id"]),
                }
            )
            updated += 1
    logger.info("saved scores for %d rooms", updated)
    return updated


def e_value(rr: float) -> float:
    """
    E-value: 未観測交絡が推定結果を完全に説明するために必要な
    交絡の強さ（リスク比）の最小値。

    VanderWeele & Ding (2017) の公式:
        E = RR + sqrt(RR * (RR - 1))

    Args:
        rr: 推定されたリスク比（家賃の比率として近似）

    Returns:
        E-value（これ以上の未観測交絡がなければ結果は因果的）

    使い方:
        station_distance の係数が -5000円/分 で、
        平均家賃が 150000円 とすると
        rr = 145000 / 150000 ≈ 0.967
        e_value(1/0.967) で「どの程度の未観測交絡があれば結果が消えるか」を確認
    """
    if rr < 1:
        rr = 1 / rr
    return round(rr + math.sqrt(rr * (rr - 1)), 3)
