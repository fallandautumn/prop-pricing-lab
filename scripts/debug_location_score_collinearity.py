"""
適正価格モデルにおけるlocation_scoreの反直感的な負係数(area_group込みで-2.22%, p=0.074)
を検証する診断スクリプト。

検証する仮説は2つ:

1. 【当初の仮説】area_group（町名固定効果）とlocation_scoreの多重共線性
   location_scoreはLLMが町名だけを見て採点しているため、area_group固定効果と
   説明力が重複している可能性がある。VIF（分散拡大係数）で定量化する。

2. 【今回追加で疑う点】building単位の変数をroom単位モデルに投入することによる
   標準誤差の過小評価（クラスタリング未考慮）
   brand_score・location_score・station_distance・age・total_floorsは
   すべてbuilding単位の属性で、同一建物内のroomでは全く同じ値になる。
   つまり実質的な独立情報の単位はroom数(2698)ではなくbuilding数(約1239)に近い。
   通常のOLSはroomを独立観測として扱うため、これらの変数の標準誤差が
   過小評価され、見かけ上の有意性が水増しされている可能性がある。
   building_id単位のクラスターロバスト標準誤差で再計算し、p値がどう動くかを見る。

実行:
  python scripts/debug_location_score_collinearity.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from patsy import dmatrices
from statsmodels.stats.outliers_influence import variance_inflation_factor

from app.db.session import engine
from app.analysis.matching import load_analysis_data
from app.analysis.scoring import FAIR_PRICE_FORMULA, _prepare_model_data


def check_vif(df_model: pd.DataFrame) -> None:
    print("=" * 60)
    print("【検証1】VIF（分散拡大係数） — area_group等との多重共線性")
    print("=" * 60)
    y, X = dmatrices(FAIR_PRICE_FORMULA, data=df_model, return_type="dataframe")

    vifs = []
    for i, col in enumerate(X.columns):
        try:
            vif = variance_inflation_factor(X.values, i)
        except Exception:
            vif = float("nan")
        vifs.append((col, vif))

    # 主要な連続変数だけ抜粋して表示（ダミー変数は数が多いので除く）
    key_vars = [
        "station_distance", "floor", "np.log(liv_area)", "age",
        "total_floors", "brand_score", "location_score",
    ]
    print(f"{'変数':<25}{'VIF':>10}")
    for col, vif in vifs:
        if col in key_vars:
            print(f"{col:<25}{vif:>10.2f}")

    print(
        "\n目安: VIF>10で深刻な多重共線性、5〜10でやや注意。"
        "location_scoreがこの範囲に入っているかを確認する。"
    )


def check_clustered_se(df_model: pd.DataFrame) -> None:
    print("\n" + "=" * 60)
    print("【検証2】building_id単位クラスターロバスト標準誤差")
    print("=" * 60)

    model_default = smf.ols(FAIR_PRICE_FORMULA, data=df_model).fit()
    model_clustered = smf.ols(FAIR_PRICE_FORMULA, data=df_model).fit(
        cov_type="cluster", cov_kwds={"groups": df_model["building_id"]}
    )

    key_vars = [
        "station_distance", "floor", "np.log(liv_area)", "age",
        "total_floors", "brand_score", "location_score",
    ]
    print(f"{'変数':<20}{'係数(%)':>10}{'通常SE p値':>14}{'クラスターSE p値':>18}")
    for v in key_vars:
        if v not in model_default.params:
            continue
        coef = model_default.params[v]
        pct = coef if "log" in v else (np.exp(coef) - 1) * 100
        p_default = model_default.pvalues[v]
        p_cluster = model_clustered.pvalues[v]
        print(f"{v:<20}{pct:>10.2f}{p_default:>14.4f}{p_cluster:>18.4f}")

    n_buildings = df_model["building_id"].nunique()
    print(
        f"\nroom数={len(df_model)} / building数={n_buildings}。"
        f"brand_score・location_score・station_distance・age・total_floorsは"
        f"building単位で不変のため、実質的な独立情報量はbuilding数に近い。"
        f"通常のOLSはroom数を独立観測として扱うため標準誤差を過小評価しうる。"
    )


def check_without_area_group(df_model: pd.DataFrame) -> None:
    print("\n" + "=" * 60)
    print("【検証3】area_groupを外した場合のlocation_score係数の変化")
    print("=" * 60)

    formula_with = FAIR_PRICE_FORMULA
    formula_without = (
        "log_price ~ station_distance + floor + np.log(liv_area) + age"
        " + total_floors + brand_score + location_score"
        " + C(floor_plan_cat) + C(building_type_cat)"
    )

    m_with = smf.ols(formula_with, data=df_model).fit()
    m_without = smf.ols(formula_without, data=df_model).fit()

    for label, m in [("area_group込み", m_with), ("area_groupなし", m_without)]:
        coef = m.params["location_score"]
        pct = (np.exp(coef) - 1) * 100
        pval = m.pvalues["location_score"]
        print(f"  {label}: location_score = {pct:+.2f}% (p={pval:.4f})")


if __name__ == "__main__":
    df = load_analysis_data(engine)
    df_model = _prepare_model_data(df)
    print(f"分析対象: {len(df_model)} rooms / {df_model['building_id'].nunique()} buildings\n")

    check_vif(df_model)
    check_clustered_se(df_model)
    check_without_area_group(df_model)
