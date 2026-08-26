"""
scoring.py の適正価格モデル（room-level、実際にestimated_price/divergence_rateを
算出する予測モデル）で、C(area_group)をlocation_scoreに置き換えると
予測性能がどう変わるかを検証する。

matching.py（因果推論用）とは別のモデルなので、debug_area_group_vs_location_score.py
とは別に検証する。予測モデルなので in-sample の R²/AIC だけでなく
building単位 K-fold CV による out-of-sample R²/RMSE も比較する
（過学習しているかどうかは in-sample 指標だけでは分からないため）。

3パターン:
  1. 現状: C(area_group) + location_score 両方
  2. area_groupのみ（location_score抜き）
  3. location_scoreのみ（area_group抜き）

実行:
  python scripts/debug_area_group_vs_location_score_scoring.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from app.db.session import engine
from app.analysis.matching import load_analysis_data
from app.analysis.scoring import _prepare_model_data, _building_kfold_splits, CAT_COLS


FORMULAS = {
    "現状(area_group + location_score)": (
        "log_price ~ station_distance + floor + np.log(liv_area) + age"
        " + total_floors + brand_score + location_score"
        " + C(area_group) + C(floor_plan_cat) + C(building_type_cat)"
    ),
    "area_groupのみ": (
        "log_price ~ station_distance + floor + np.log(liv_area) + age"
        " + total_floors + brand_score"
        " + C(area_group) + C(floor_plan_cat) + C(building_type_cat)"
    ),
    "location_scoreのみ": (
        "log_price ~ station_distance + floor + np.log(liv_area) + age"
        " + total_floors + brand_score + location_score"
        " + C(floor_plan_cat) + C(building_type_cat)"
    ),
}

# location_scoreのみモデルはarea_groupを使わないのでCAT_COLSからも外す
CAT_COLS_MAP = {
    "現状(area_group + location_score)": CAT_COLS,
    "area_groupのみ": CAT_COLS,
    "location_scoreのみ": [c for c in CAT_COLS if c != "area_group"],
}


def run_cv(df_model: pd.DataFrame, formula: str, cat_cols: list[str], n_splits: int = 5, random_state: int = 42) -> dict:
    fold_test_ids = _building_kfold_splits(df_model, n_splits, random_state)
    r2s, rmses = [], []

    for test_ids in fold_test_ids:
        train_df = df_model[~df_model["building_id"].isin(test_ids)]
        test_df = df_model[df_model["building_id"].isin(test_ids)]
        if len(train_df) < 50 or len(test_df) < 5:
            continue

        mask = pd.Series(True, index=test_df.index)
        for col in cat_cols:
            known = set(train_df[col].unique())
            mask &= test_df[col].isin(known)
        test_known = test_df[mask]
        if len(test_known) < 3:
            continue

        try:
            model = smf.ols(formula, data=train_df).fit()
            pred = model.predict(test_known)
        except Exception:
            continue

        residual = test_known["log_price"].values - pred.values
        rmse = float(np.sqrt(np.mean(residual ** 2)))
        ss_res = float(np.sum(residual ** 2))
        ss_tot = float(np.sum((test_known["log_price"].values - test_known["log_price"].values.mean()) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
        r2s.append(r2)
        rmses.append(rmse)

    return {
        "mean_r2": round(float(np.mean(r2s)), 3) if r2s else None,
        "mean_rmse": round(float(np.mean(rmses)), 4) if rmses else None,
        "n_folds": len(r2s),
    }


if __name__ == "__main__":
    df = load_analysis_data(engine)
    df_model = _prepare_model_data(df)
    print(f"分析対象: {len(df_model)} rooms / {df_model['building_id'].nunique()} buildings\n")

    for label, formula in FORMULAS.items():
        model = smf.ols(formula, data=df_model).fit()
        cv = run_cv(df_model, formula, CAT_COLS_MAP[label])

        print(f"--- {label} ---")
        print(f"  パラメータ数(k): {int(model.df_model) + 1}")
        print(f"  in-sample  R²={model.rsquared:.3f}  adjR²={model.rsquared_adj:.3f}  "
              f"AIC={model.aic:.1f}  BIC={model.bic:.1f}")
        print(f"  out-of-sample(5fold CV)  R²={cv['mean_r2']}  RMSE={cv['mean_rmse']}  "
              f"(成功fold数={cv['n_folds']})")
        print()
