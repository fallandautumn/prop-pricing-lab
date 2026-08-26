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

=== 検証について ===
このモデルは予測モデル（適正価格の予測）なので、因果効果モデルと違って
train/testでの検証が必要。特に C(area_group) は町名によっては建物数が
1〜2棟しかなく、その建物固有の価格をほぼ「暗記」してしまうリークの
リスクがある。対策として:
  1. 建物数が少ない area_group は区レベルにまとめる（_collapse_rare_area_groups）
  2. evaluate_fair_price_model_cv() で building 単位の K-fold CV を行い、
     out-of-sample R²/RMSE を報告する（モデル仕様の妥当性を見る診断用）

=== 本番スコアリング: in-sampleではなくout-of-fold予測を使う ===
build_fair_price_model()は全データで学習する。もしこのモデルで
「学習に使った同じデータ」をそのまま採点すると、ある建物の価格が
C(area_group)等の固定効果を通じて自分自身の「適正価格」に混ざり込む
（学習データ=推定データ問題）。evaluate_fair_price_model_cv()は
診断（集計指標を見るだけ）であり、この問題を解決しない。

本番の divergence_rate は compute_out_of_fold_scores() で計算する。
これは building 単位の K-fold に分け、各建物は「自分を含まないfoldで
学習したモデル」から予測値を得る（out-of-fold prediction）。
Double Machine LearningのCross-fittingと同じ発想: 効果の解釈用の
係数（build_fair_price_modelの出力）は全データ学習のままでよいが、
スコアリング（推定値の算出）だけは学習データと分離する。
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

FAIR_PRICE_FORMULA = (
    "log_price ~ station_distance + floor + np.log(liv_area) + age"
    " + total_floors + brand_score"
    " + C(area_group) + C(floor_plan_cat) + C(building_type_cat)"
)
# location_scoreは2026-08-26時点でモデルから除外した。VIF=12.04でarea_groupと
# 深刻な多重共線性があり、クラスターロバストSEではp=0.28へ後退、area_group抜きでは
# 符号が反転する（+10%超）ことを確認。area_groupをlocation_scoreに置き換える比較でも
# in-sample R²・out-of-sample R²/RMSE・AIC・BICのすべてが悪化した
# （scripts/debug_area_group_vs_location_score_scoring.py）。location_scoreは
# 入力が町名のみのため、area_groupと本質的に同じ情報源から作られており、
# 当初期待していた「area_groupとは独立な補完情報」にはならなかった。
# brand_scoreはVIF=1.37程度で問題なく、そのまま残している。

MIN_AREA_GROUP_BUILDINGS = 3  # これ未満の建物数しかない町名は区レベルに統合する
CAT_COLS = ["area_group", "floor_plan_cat", "building_type_cat"]  # unseen category判定対象


def _building_kfold_splits(df_model: pd.DataFrame, n_splits: int, random_state: int) -> list[set]:
    """building_id を n_splits 分割し、各foldのtest用building_id集合のリストを返す。"""
    building_ids = df_model["building_id"].unique().copy()
    rng = np.random.RandomState(random_state)
    rng.shuffle(building_ids)
    return [set(f) for f in np.array_split(building_ids, n_splits)]


def _collapse_rare_area_groups(df_model: pd.DataFrame, min_buildings: int = MIN_AREA_GROUP_BUILDINGS) -> pd.Series:
    """
    建物数が少ない area_group（町名）を区レベル（例: "東京都渋谷区"）に統合する。
    小さすぎるグループは固定効果がその建物の価格をほぼ暗記してしまい、
    divergence_rateが不当に0に近づくリーク・過学習の原因になるため。
    """
    counts = df_model.groupby("area_group")["building_id"].nunique()
    rare = set(counts[counts < min_buildings].index)
    if not rare:
        return df_model["area_group"]

    ward = df_model["address"].str.extract(r"(東京都.+?[区市])")[0]
    collapsed = df_model["area_group"].where(~df_model["area_group"].isin(rare), ward)
    logger.info(
        "area_group: %d/%d groups (建物数<%d) を区レベルに統合",
        len(rare), len(counts), min_buildings,
    )
    return collapsed


def _prepare_model_data(df: pd.DataFrame) -> pd.DataFrame:
    """適正価格モデル用データを準備する（build_fair_price_model / CV共通）。"""
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
        "brand_score",
    ]
    df_model = df.dropna(subset=required).copy()
    df_model = df_model[
        (df_model["price"] > 0) & (df_model["liv_area"] > 0)
    ]
    df_model["log_price"] = np.log(df_model["price"])
    df_model["area_group"] = _collapse_rare_area_groups(df_model)
    return df_model


def build_fair_price_model(df: pd.DataFrame):
    """DAGに基づく適正価格モデルを構築する（log(price) を目的変数とする）。

    - np.log(liv_area) による両対数化で外挿エラーを防止
    - C(area_group) による町名レベル固定効果で立地交絡を制御
      （建物数が少ないグループは区レベルに統合してリークを抑制）

    本番用: 全データで学習する（out-of-sample検証は evaluate_fair_price_model_cv() を参照）。
    """
    df_model = _prepare_model_data(df)

    n = len(df_model)
    logger.info("fair price model: %d rooms", n)

    if n < 50:
        raise ValueError(
            f"モデル構築に必要なデータが不足しています（現在 {n} 件、50件以上必要）"
        )

    model = smf.ols(FAIR_PRICE_FORMULA, data=df_model).fit()

    key_vars = [
        "station_distance",
        "floor",
        "np.log(liv_area)",
        "age",
        "total_floors",
        "brand_score",
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

def evaluate_fair_price_model_cv(df: pd.DataFrame, n_splits: int = 5, random_state: int = 42) -> dict:
    """
    適正価格モデルの building 単位 K-fold CV による out-of-sample 評価。

    room単位でランダム分割すると同じ建物のroomがtrain/test両方に入り、
    area_group等の固定効果を通じてリークするため、building_id単位で分割する。

    C(area_group)等のカテゴリ変数はtrainに存在しない水準がtestに出ると
    予測できない（patsyがUnseen categoryでエラーになる）ため、
    そのようなrowはこのfoldの評価から除外し、除外件数を報告する。

    本番の save_scores() には一切影響しない（診断専用）。

    Returns:
        n_splits         : fold数
        fold_metrics      : fold毎の [r2, rmse, mae, n_test_used, n_test_dropped]
        mean_r2 / std_r2  : out-of-sample R²の平均・標準偏差
        mean_rmse         : out-of-sample RMSE（log_price単位）の平均
        train_r2          : 参考: 全データ学習時のin-sample R²（build_fair_price_modelと同じ）
    """
    df_model = _prepare_model_data(df)
    fold_test_ids = _building_kfold_splits(df_model, n_splits, random_state)

    fold_metrics = []
    for i, test_ids in enumerate(fold_test_ids):
        train_df = df_model[~df_model["building_id"].isin(test_ids)]
        test_df = df_model[df_model["building_id"].isin(test_ids)]

        if len(train_df) < 50 or len(test_df) < 5:
            logger.warning("cv fold %d: データ不足のためスキップ", i)
            continue

        # trainに存在しないカテゴリ水準を持つtest行は予測不能なので除外する
        mask = pd.Series(True, index=test_df.index)
        for col in CAT_COLS:
            known = set(train_df[col].unique())
            mask &= test_df[col].isin(known)
        test_known = test_df[mask]
        n_dropped = len(test_df) - len(test_known)

        if len(test_known) < 3:
            logger.warning("cv fold %d: 予測可能なtest行が不足のためスキップ", i)
            continue

        try:
            model = smf.ols(FAIR_PRICE_FORMULA, data=train_df).fit()
            pred = model.predict(test_known)
        except Exception as e:
            logger.warning("cv fold %d: 学習/予測に失敗: %s", i, e)
            continue

        residual = test_known["log_price"].values - pred.values
        rmse = float(np.sqrt(np.mean(residual ** 2)))
        mae = float(np.mean(np.abs(residual)))
        ss_res = float(np.sum(residual ** 2))
        ss_tot = float(np.sum((test_known["log_price"].values - test_known["log_price"].values.mean()) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")

        fold_metrics.append({
            "fold": i,
            "r2": round(r2, 3),
            "rmse": round(rmse, 4),
            "mae": round(mae, 4),
            "n_test_used": len(test_known),
            "n_test_dropped": n_dropped,
        })
        logger.info(
            "cv fold %d: R²=%.3f RMSE=%.4f (test=%d件, unseen category除外=%d件)",
            i, r2, rmse, len(test_known), n_dropped,
        )

    if not fold_metrics:
        return {"error": "全foldで評価に失敗しました"}

    r2s = [f["r2"] for f in fold_metrics]
    rmses = [f["rmse"] for f in fold_metrics]

    # 参考: in-sample R²（全データ学習）
    full_model = smf.ols(FAIR_PRICE_FORMULA, data=df_model).fit()

    return {
        "n_splits": len(fold_metrics),
        "fold_metrics": fold_metrics,
        "mean_r2": round(float(np.mean(r2s)), 3),
        "std_r2": round(float(np.std(r2s, ddof=1)), 3) if len(r2s) > 1 else None,
        "mean_rmse": round(float(np.mean(rmses)), 4),
        "train_r2": round(float(full_model.rsquared), 3),
    }


def compute_arbitrage_scores(df_model: pd.DataFrame, model) -> pd.DataFrame:
    """
    【診断・参考用】in-sampleでの適正価格と裁定スコアを計算する。

    学習に使ったのと同じデータを同じモデルで予測するため、
    本番のスコアリングには使わないこと（compute_out_of_fold_scores()を使う）。
    係数の解釈やモデルの当てはまり確認用。

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
        "arbitrage(in-sample・参考): 割安(>5%%)=%d件 割高(>5%%)=%d件 / 全%d件",
        len(neg), len(pos), len(df_out)
    )

    return df_out[["room_id", "price", "estimated_price", "divergence_rate"]]


def compute_out_of_fold_scores(df: pd.DataFrame, n_splits: int = 5, random_state: int = 42) -> pd.DataFrame:
    """
    【本番用】out-of-fold予測による適正価格・裁定スコアの算出。

    building単位のK-foldに分け、各buildingは「自分を含まないfoldで学習した
    モデル」から予測を得る（Double MLのcross-fittingと同じ発想）。
    これにより「学習データ=推定データ」問題を解消する。

    trainに存在しないカテゴリ水準（area_group等）を持つ行は、そのfoldでは
    予測できないため、フォールバックとして全データ学習モデル（in-sample）の
    予測値を使う。フォールバックが使われた件数は is_out_of_fold=False で
    判別できる（通常ごく少数）。

    Returns:
        room_id, price, estimated_price, divergence_rate, is_out_of_fold を含むDataFrame
    """
    df_model = _prepare_model_data(df)
    fold_test_ids = _building_kfold_splits(df_model, n_splits, random_state)

    # unseen categoryでout-of-fold予測できない行のフォールバック用（全データ学習）
    fallback_model = smf.ols(FAIR_PRICE_FORMULA, data=df_model).fit()

    rows = []
    for i, test_ids in enumerate(fold_test_ids):
        train_df = df_model[~df_model["building_id"].isin(test_ids)]
        test_df = df_model[df_model["building_id"].isin(test_ids)]
        if len(test_df) == 0:
            continue

        if len(train_df) < 50:
            logger.warning("oof fold %d: 学習データ不足、全件フォールバック", i)
            test_known = test_df.iloc[0:0]
            test_unknown = test_df
        else:
            mask = pd.Series(True, index=test_df.index)
            for col in CAT_COLS:
                known = set(train_df[col].unique())
                mask &= test_df[col].isin(known)
            test_known = test_df[mask]
            test_unknown = test_df[~mask]

            if len(test_known) > 0:
                try:
                    fold_model = smf.ols(FAIR_PRICE_FORMULA, data=train_df).fit()
                    pred = np.exp(fold_model.predict(test_known))
                    for room_id, price, ep in zip(test_known["room_id"], test_known["price"], pred):
                        rows.append((room_id, price, ep, True))
                except Exception as e:
                    logger.warning("oof fold %d: 学習/予測に失敗、全件フォールバック: %s", i, e)
                    test_unknown = test_df

        if len(test_unknown) > 0:
            pred = np.exp(fallback_model.predict(test_unknown))
            for room_id, price, ep in zip(test_unknown["room_id"], test_unknown["price"], pred):
                rows.append((room_id, price, ep, False))

    df_out = pd.DataFrame(rows, columns=["room_id", "price", "estimated_price", "is_out_of_fold"])
    df_out["estimated_price"] = df_out["estimated_price"].round().astype(int)
    df_out["divergence_rate"] = (
        (df_out["price"] - df_out["estimated_price"]) / df_out["estimated_price"]
    ).round(4)

    n_oof = int(df_out["is_out_of_fold"].sum())
    n_fallback = len(df_out) - n_oof
    logger.info(
        "out-of-fold scoring: 全%d件（真のout-of-fold=%d件, フォールバック(in-sample)=%d件）",
        len(df_out), n_oof, n_fallback,
    )

    neg = df_out[df_out["divergence_rate"] < -0.05]
    pos = df_out[df_out["divergence_rate"] > 0.05]
    logger.info(
        "arbitrage(out-of-fold): 割安(>5%%)=%d件 割高(>5%%)=%d件 / 全%d件",
        len(neg), len(pos), len(df_out)
    )

    return df_out[["room_id", "price", "estimated_price", "divergence_rate", "is_out_of_fold"]]


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
