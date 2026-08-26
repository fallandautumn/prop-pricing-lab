"""
CEM (Coarsened Exact Matching) による①駅徒歩効果の再推定。

matching.py の共変量調整OLSとは異なる識別戦略。連続変数を粗いビン
（quantileベース）に離散化し、同じビンの組み合わせ（ストラータム）内で
のみ比較することで、線形性・関数形の仮定に頼らずに交絡を制御する。

=== 連続処置を二値化する理由 ===
CEM（Iacus, King, Porro）は本来二値処置を前提とする手法。station_distance
は連続変数（分）なので、中央値で「駅近(treatment=1)」「駅遠(treatment=0)」
に二値化して扱う。1分あたりの限界効果ではなく「駅近であることの効果」
という粗い推定になる点に注意（OLSの-0.24%/分とは解釈の粒度が異なる）。

=== area_group を厳密にマッチングすると起きる問題 ===
area_group（町名, 約26水準）を他の共変量（age/total_floors/liv_area）
と一緒に厳密一致でマッチングすると、ストラータムの組み合わせ数が
サンプルサイズに対して爆発し、ほとんどの建物が「マッチ相手なし」に
なる（次元の呪い）。これを確認するため、area_groupを含む版・含まない版
の両方を実行して比較する設計にしている。
"""
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

STRATA_COLS_BASE = ["age_bin", "floors_bin", "area_bin", "building_type_cat"]


def _prepare_cem_df(df: pd.DataFrame) -> pd.DataFrame:
    """building-level データを準備し、二値処置(駅近/駅遠)と粗いビンを付与する。"""
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
            subset=[
                "station_distance", "age", "total_floors",
                "avg_log_price", "avg_liv_area", "area_group",
            ]
        )
    )

    median_dist = bdf["station_distance"].median()
    # 駅近(1) / 駅遠(0)。中央値ちょうどは駅近側に含める。
    bdf["treatment"] = (bdf["station_distance"] <= median_dist).astype(int)

    # quantileベースの粗いビン（3分位）。固定閾値より各ビンの人数バランスが良く、
    # マッチしやすい。重複値が多い場合は duplicates="drop" でビン数が減ることがある。
    bdf["age_bin"] = pd.qcut(bdf["age"], q=3, duplicates="drop").astype(str)
    bdf["floors_bin"] = pd.qcut(bdf["total_floors"], q=3, duplicates="drop").astype(str)
    bdf["area_bin"] = pd.qcut(bdf["avg_liv_area"], q=3, duplicates="drop").astype(str)

    return bdf, float(median_dist)


def _compute_att(bdf: pd.DataFrame, strata_cols: list[str]) -> dict:
    """指定したストラータム列でCEMのATTを計算する共通ロジック。"""
    work = bdf.copy()
    work["stratum"] = work[strata_cols].astype(str).agg("|".join, axis=1)

    n_treated_total = int((work["treatment"] == 1).sum())
    n_control_total = int((work["treatment"] == 0).sum())

    matched_treated = 0
    matched_control = 0
    weighted_diff_sum = 0.0
    strata_detail = []

    for stratum, g in work.groupby("stratum"):
        treated = g[g["treatment"] == 1]
        control = g[g["treatment"] == 0]
        if len(treated) == 0 or len(control) == 0:
            continue  # マッチ相手がいないストラータムは標準的なCEMの扱いとして捨てる
        diff = treated["avg_log_price"].mean() - control["avg_log_price"].mean()
        weighted_diff_sum += diff * len(treated)
        matched_treated += len(treated)
        matched_control += len(control)
        strata_detail.append({
            "stratum": stratum,
            "n_treated": len(treated),
            "n_control": len(control),
            "log_diff": round(float(diff), 4),
        })

    n_strata_total = work["stratum"].nunique()

    if matched_treated == 0:
        return {"error": "マッチしたストラータムがありません（次元の呪い）"}

    att_log = weighted_diff_sum / matched_treated
    att_pct = (np.exp(att_log) - 1) * 100

    return {
        "att_log": att_log,
        "att_pct": round(att_pct, 2),
        "n_buildings_total": len(work),
        "n_treated_total": n_treated_total,
        "n_control_total": n_control_total,
        "n_matched_treated": matched_treated,
        "n_matched_control": matched_control,
        "treated_coverage": round(matched_treated / n_treated_total, 3) if n_treated_total else 0.0,
        "control_coverage": round(matched_control / n_control_total, 3) if n_control_total else 0.0,
        "n_strata_matched": len(strata_detail),
        "n_strata_total": n_strata_total,
        "strata_detail": strata_detail,
    }


def run_cem(df: pd.DataFrame, include_area_group: bool = True) -> dict:
    """
    CEMで①駅徒歩効果（駅近 vs 駅遠のATT）を推定する。

    Args:
        include_area_group: True なら町名(area_group)も厳密一致でマッチングする
            （立地の交絡をより厳密に制御するが、マッチ率が下がりやすい）。

    Returns:
        median_split_min : 駅近/駅遠を分けた中央値（分）
        att_pct           : ATT（駅近であることの家賃への効果、%）
        treated_coverage  : マッチできた駅近建物の割合（低いほどCEMの結果の信頼性が下がる）
        control_coverage  : マッチできた駅遠建物の割合
        n_strata_matched / n_strata_total : マッチが成立したストラータム数 / 全ストラータム数
        strata_detail     : ストラータムごとの詳細（デバッグ用）
    """
    bdf, median_dist = _prepare_cem_df(df)
    strata_cols = STRATA_COLS_BASE + (["area_group"] if include_area_group else [])

    result = _compute_att(bdf, strata_cols)
    if "error" in result:
        return result

    result["median_split_min"] = median_dist
    result["include_area_group"] = include_area_group

    logger.info(
        "CEM(area_group=%s): ATT=%+.2f%% treated_coverage=%.1f%% (%d/%d) "
        "control_coverage=%.1f%% (%d/%d) strata=%d/%d",
        include_area_group, result["att_pct"],
        result["treated_coverage"] * 100, result["n_matched_treated"], result["n_treated_total"],
        result["control_coverage"] * 100, result["n_matched_control"], result["n_control_total"],
        result["n_strata_matched"], result["n_strata_total"],
    )
    return result


def bootstrap_cem_att(
    df: pd.DataFrame, include_area_group: bool = True, n_boot: int = 200, random_state: int = 42
) -> dict:
    """
    CEM ATTのクラスターブートストラップCI（building単位で重複ありリサンプリング）。
    """
    bdf, _ = _prepare_cem_df(df)
    strata_cols = STRATA_COLS_BASE + (["area_group"] if include_area_group else [])

    rng = np.random.RandomState(random_state)
    n = len(bdf)
    boot_atts = []

    for _ in range(n_boot):
        idx = rng.randint(0, n, size=n)
        resampled = bdf.iloc[idx]
        result = _compute_att(resampled, strata_cols)
        if "error" not in result:
            boot_atts.append(result["att_pct"])

    if len(boot_atts) < n_boot * 0.5:
        logger.warning("CEM bootstrap: only %d/%d iterations succeeded", len(boot_atts), n_boot)

    arr = np.array(boot_atts)
    return {
        "n_boot_success": len(arr),
        "boot_mean_pct": round(float(arr.mean()), 2) if len(arr) else None,
        "boot_se_pct": round(float(arr.std(ddof=1)), 2) if len(arr) > 1 else None,
        "boot_ci_95_pct": (
            [round(float(np.percentile(arr, 2.5)), 2), round(float(np.percentile(arr, 97.5)), 2)]
            if len(arr) else None
        ),
    }
