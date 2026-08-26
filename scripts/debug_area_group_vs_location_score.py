"""
matching.py の①駅徒歩効果モデル（building-level）で、C(area_group)を
location_scoreに置き換えると「精度」がどう変わるかを実際に比較する。

3パターンを比較:
  1. 現状: C(area_group) + location_score 両方
  2. area_groupのみ（location_score抜き）
  3. location_scoreのみ（area_group抜き）

見るべき指標:
  - station_distanceの係数・SE・p値（本来の分析対象）
  - R²（当てはまりの良さ）
  - AIC/BIC（パラメータ数を罰則化した上でのモデル選択指標）
  - 使用building数

実行:
  python scripts/debug_area_group_vs_location_score.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import numpy as np
import statsmodels.formula.api as smf

from app.db.session import engine
from app.analysis.matching import load_analysis_data, _prepare_station_level_df


FORMULAS = {
    "現状(area_group + location_score)": (
        "avg_log_price ~ station_distance + age + total_floors"
        " + np.log(avg_liv_area) + brand_score + location_score"
        " + C(building_type_cat) + C(area_group)"
    ),
    "area_groupのみ": (
        "avg_log_price ~ station_distance + age + total_floors"
        " + np.log(avg_liv_area) + brand_score"
        " + C(building_type_cat) + C(area_group)"
    ),
    "location_scoreのみ": (
        "avg_log_price ~ station_distance + age + total_floors"
        " + np.log(avg_liv_area) + brand_score + location_score"
        " + C(building_type_cat)"
    ),
}


if __name__ == "__main__":
    df = load_analysis_data(engine)
    bdf = _prepare_station_level_df(df)
    print(f"building数: {len(bdf)}\n")

    for label, formula in FORMULAS.items():
        model = smf.ols(formula, data=bdf).fit()
        coef = model.params["station_distance"]
        se = model.bse["station_distance"]
        pval = model.pvalues["station_distance"]
        ci = model.conf_int().loc["station_distance"]
        pct = (np.exp(coef) - 1) * 100
        ci_pct = [(np.exp(ci[0]) - 1) * 100, (np.exp(ci[1]) - 1) * 100]

        print(f"--- {label} ---")
        print(f"  パラメータ数(k): {int(model.df_model) + 1}")
        print(f"  station_distance: {pct:+.2f}%  SE(log)={se:.4f}  p={pval:.4f}  "
              f"CI=[{ci_pct[0]:+.2f}%, {ci_pct[1]:+.2f}%]")
        print(f"  R²={model.rsquared:.3f}  adjR²={model.rsquared_adj:.3f}  "
              f"AIC={model.aic:.1f}  BIC={model.bic:.1f}")
        print()
