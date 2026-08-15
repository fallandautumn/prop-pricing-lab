"""Phase 1 因果効果推定

②階数効果: 建物固定効果（FE）回帰
    log_price ~ floor + np.log(liv_area) + C(floor_plan) + C(building_id)
    同一建物内比較により立地・築年数・構造を自動制御（%効果に標準化）

①駅徒歩効果: 共変量調整OLS（building-level）
    avg_log_price ~ station_distance + age + total_floors + avg_liv_area
    バックドア調整集合 {age, total_floors} を制御
"""

import logging
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# 間取りを大カテゴリに集約
FLOOR_PLAN_MAP = {
    "ワンルーム": "1R",
    "1K": "1K",
    "1DK": "1DK",
    "1LDK": "1LDK",
    "2K": "2K以上",
    "2DK": "2K以上",
    "2LDK": "2K以上",
    "3K": "3K以上",
    "3DK": "3K以上",
    "3LDK": "3K以上",
}


def load_analysis_data(engine: Engine) -> pd.DataFrame:
    """rooms + buildings を結合して分析用 DataFrame を返す。

    price IS NOT NULL かつ price > 0 のレコードのみ対象。
    """
    query = text("""
        SELECT
            r.id        AS room_id,
            r.price,
            r.floor,
            r.liv_area,
            r.floor_plan,
            r.building_id,
            b.station_distance,
            b.age,
            b.total_floors,
            b.building_structure,
            b.building_type,
            b.title,
            b.address
        FROM rooms r
        JOIN buildings b ON r.building_id = b.id
        WHERE r.price IS NOT NULL AND r.price > 0
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    df["log_price"] = np.log(df["price"])
    df["floor_plan_cat"] = df["floor_plan"].map(FLOOR_PLAN_MAP).fillna("other")
    df["building_type_cat"] = (
        df["building_type"].fillna("不明").replace("", "不明")
    )
    # 町名レベル固定効果用（例: "東京都渋谷区笹塚３" -> "東京都渋谷区笹塚"）。
    # 立地プレミアム（DAGのlocation_U）のプロキシとして station_distance の
    # 推定・適正価格モデル双方で共通に使う。
    df["area_group"] = df["address"].str.extract(r"(東京都.+?[区市].+?[一-龠]+)")

    logger.info(
        "loaded %d rooms across %d buildings",
        len(df),
        df["building_id"].nunique(),
    )
    return df


def estimate_floor_effect(df: pd.DataFrame) -> dict:
    """階数が家賃に与える因果効果（建物固定効果モデル - log-price）

    識別: C(building_id) で建物レベルの全交絡を制御
    条件: 同一建物に3部屋以上あること

    Returns:
        floor_pct_effect : 1階上がるごとの家賃変化率（%）
        floor_pval       : p値
        ci_95_pct        : 95%信頼区間 [%]
        n_rooms          : 使用した部屋数
        n_buildings      : 使用した建物数（3部屋以上）
        r2               : 決定係数
    """
    counts = df.groupby("building_id")["room_id"].count()
    valid_ids = counts[counts >= 3].index
    df_fe = df[
        df["building_id"].isin(valid_ids)
        & df["floor"].notna()
        & df["liv_area"].notna()
        & (df["liv_area"] > 0)
    ].copy()

    n_buildings = df_fe["building_id"].nunique()
    logger.info(
        "floor effect: %d rooms in %d buildings (>=3 rooms)",
        len(df_fe),
        n_buildings,
    )

    if len(df_fe) < 30 or n_buildings < 5:
        logger.warning("floor effect: insufficient data")
        return {"error": "有効データ不足（3部屋以上の建物が5棟以上必要）"}

    formula = "log_price ~ floor + np.log(liv_area) + C(floor_plan_cat) + C(building_id)"
    result = smf.ols(formula, data=df_fe).fit()

    coef = result.params.get("floor")
    pval = result.pvalues.get("floor")
    ci = (
        result.conf_int().loc["floor"].tolist()
        if "floor" in result.conf_int().index
        else [0, 0]
    )

    # Log-Linear のため % 効果に変換
    pct_effect = (np.exp(coef) - 1) * 100
    ci_pct = [(np.exp(ci[0]) - 1) * 100, (np.exp(ci[1]) - 1) * 100]

    logger.info(
        "floor coef=%+.2f%%/階 p=%.3f CI=[%+.2f%%, %+.2f%%]",
        pct_effect,
        pval,
        ci_pct[0],
        ci_pct[1],
    )
    return {
        "floor_pct_effect": round(pct_effect, 2),
        "floor_pval": round(pval, 4),
        "ci_95_pct": [round(ci_pct[0], 2), round(ci_pct[1], 2)],
        "n_rooms": len(df_fe),
        "n_buildings": n_buildings,
        "r2": round(result.rsquared, 3),
    }


def estimate_station_distance_effect(df: pd.DataFrame) -> dict:
    """駅徒歩が家賃に与える因果効果（共変量調整OLS - log-price）

    バックドア調整集合: {age, total_floors, avg_liv_area}
    単位: building-level（1建物 = 1観測）で推定

    Returns:
        station_pct_effect: 駅徒歩1分増加あたりの家賃変化率（%）
        station_pval      : p値
        ci_95_pct         : 95%信頼区間 [%]
        n_buildings       : 使用建物数
        r2                : R²
    """
    df_valid = df[df["liv_area"] > 0].copy()
    bdf = (
        df_valid.groupby("building_id")
        .agg(
            station_distance=("station_distance", "first"),
            age=("age", "first"),
            total_floors=("total_floors", "first"),
            building_type_cat=("building_type_cat", "first"),
            area_group=("area_group", "first"),
            avg_log_price=("log_price", "mean"),
            avg_liv_area=("liv_area", "mean"),
        )
        .reset_index()
        .dropna(
            subset=["station_distance", "age", "avg_log_price", "avg_liv_area", "area_group"]
        )
    )

    logger.info("station distance effect: %d buildings", len(bdf))

    if len(bdf) < 20:
        logger.warning("station effect: insufficient buildings")
        return {"error": "有効建物数不足（20棟以上必要）"}

    # area_group（町名レベル固定効果）を制御することで立地プレミアムの
    # 未観測交絡を減らす。これを入れないと station_distance の符号が
    # 逆転する（駅から遠いほど高い、という反直感的な結果になる）ことを確認済み。
    formula = (
        "avg_log_price ~ station_distance + age + total_floors"
        " + np.log(avg_liv_area) + C(building_type_cat) + C(area_group)"
    )
    result = smf.ols(formula, data=bdf).fit()

    coef = result.params.get("station_distance")
    pval = result.pvalues.get("station_distance")
    ci = result.conf_int().loc["station_distance"].tolist()

    pct_effect = (np.exp(coef) - 1) * 100
    ci_pct = [(np.exp(ci[0]) - 1) * 100, (np.exp(ci[1]) - 1) * 100]

    logger.info(
        "station coef=%+.2f%%/分 p=%.3f CI=[%+.2f%%, %+.2f%%]",
        pct_effect,
        pval,
        ci_pct[0],
        ci_pct[1],
    )
    return {
        "station_pct_effect": round(pct_effect, 2),
        "station_pval": round(pval, 4),
        "ci_95_pct": [round(ci_pct[0], 2), round(ci_pct[1], 2)],
        "n_buildings": len(bdf),
        "r2": round(result.rsquared, 3),
        "confounders": ["age", "total_floors", "avg_liv_area"],
        "note": (
            "未観測交絡（立地プレミアム）が残る。感度分析は scoring.py の"
            " e_value() を参照"
        ),
    }