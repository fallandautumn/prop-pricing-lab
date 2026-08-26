"""
適正価格モデル(room単位)のstation_distanceが p=0.0006 と有意に見える件について、
location_scoreの検証と同じ手法（building単位クラスターロバストSE）で
過大評価されていないかを確認する。

station_distanceはbuilding単位で不変の変数なので、room単位の通常OLSは
標準誤差を過小評価している可能性がある。

実行:
  python scripts/check_station_clustered_se.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import numpy as np
import statsmodels.formula.api as smf

from app.db.session import engine
from app.analysis.matching import load_analysis_data
from app.analysis.scoring import FAIR_PRICE_FORMULA, _prepare_model_data


if __name__ == "__main__":
    df = load_analysis_data(engine)
    df_model = _prepare_model_data(df)

    model_default = smf.ols(FAIR_PRICE_FORMULA, data=df_model).fit()
    model_clustered = smf.ols(FAIR_PRICE_FORMULA, data=df_model).fit(
        cov_type="cluster", cov_kwds={"groups": df_model["building_id"]}
    )

    for v in ["station_distance", "brand_score"]:
        coef = model_default.params[v]
        pct = (np.exp(coef) - 1) * 100
        p_default = model_default.pvalues[v]
        p_cluster = model_clustered.pvalues[v]
        print(f"{v}: {pct:+.2f}%  通常SE p={p_default:.4f}  クラスターSE p={p_cluster:.4f}")
