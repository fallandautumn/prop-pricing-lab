"""
Phase 3（docs/phase3_summary.md）のEDAで観察した「駅徒歩効果の町別異質性」を
数値的に検証する。practice/practice.ipynbのsns.lmplotは可視化のみで、
係数・p値を算出しておらず、クラスタ構造（station_distanceはbuilding単位で
不変）も無視しているため、以下の3点を数値で埋める。

0. 分散の分解（between/within）: station_distanceの全体分散のうち、
   「町間の違い」と「町内の違い」がそれぞれどれだけを占めるか。
   C(area_group)固定効果が実際に使える情報量（within分散）は全体の
   標準偏差（ヒストグラムで見た3.02分）よりずっと小さい可能性があり、
   これが小さすぎる場合、交互作用項の検定自体が原理的に無意味になる。
   他の検証より先にこれを見て、以降の検定に進む価値があるか判断する。
1. 疑似反復の確認: 町ごとのroom数とbuilding数（room数だけ見ると独立情報量を
   過大評価する）。
2. 交互作用の統計的検定: station_distance × C(area_group) の交互作用項が
   共同でゼロと言えるか（building単位クラスターロバストSE）を、
   liv_area追加前後で比較。「liv_areaを入れると異質性が消える」という
   Phase3の解釈を、可視化ではなく検定で確認する。
3. 町別の駅徒歩スロープ: 平米単価（log(price/liv_area)）を目的変数にした
   場合の、町ごとの駅徒歩係数と（クラスター）p値。Hirooの残存する
   わずかな正の傾きが統計的に意味を持つ水準か確認する。

対象は本番の area_group（app.analysis.matching.load_analysis_data）を
使う。practice.ipynbの簡易正規表現（`渋谷区([^\\d０-９丁目番]+)`）とは
実装が異なるため、上位6町の顔ぶれ・件数がPhase3のドキュメントとは
多少ずれる可能性がある。

実行:
  python scripts/check_station_town_heterogeneity.py
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

TOP_N_TOWNS = 6


def cluster_kwds(df):
    return {"groups": df["building_id"]}


if __name__ == "__main__":
    df = load_analysis_data(engine)
    df = df.dropna(subset=["area_group", "station_distance", "liv_area", "price"]).copy()

    top_towns = df["area_group"].value_counts().head(TOP_N_TOWNS).index.tolist()
    df_top = df[df["area_group"].isin(top_towns)].copy()
    df_top["log_rent_per_m2"] = np.log(df_top["price"] / df_top["liv_area"])

    # --- 0. 分散の分解（between/within） ---
    def variance_decomposition(data: pd.DataFrame, group_col: str, value_col: str, label: str):
        overall_mean = data[value_col].mean()
        overall_std = data[value_col].std()
        group_means = data.groupby(group_col)[value_col].transform("mean")
        between_ss = ((group_means - overall_mean) ** 2).sum()
        within_ss = ((data[value_col] - group_means) ** 2).sum()
        total_ss = between_ss + within_ss
        within_std = np.sqrt(within_ss / (len(data) - data[group_col].nunique()))
        print(f"  [{label}] n={len(data)}, n_groups={data[group_col].nunique()}")
        print(f"    全体の標準偏差: {overall_std:.3f}分")
        print(f"    between（町間）が占める割合: {between_ss / total_ss * 100:.1f}%")
        print(f"    within（町内）が占める割合:  {within_ss / total_ss * 100:.1f}%")
        print(f"    within標準偏差（町内のばらつきのみ）: {within_std:.3f}分")

    print("=== 0. station_distance の分散分解（between町間 / within町内） ===")
    print("    ※ within分散が小さいほど、C(area_group)を入れた後にstation_distanceの")
    print("       係数推定に使える情報が乏しく、交互作用項の検定も原理的に無意味に近づく。")
    variance_decomposition(df_top, "area_group", "station_distance", "上位6町のみ（このEDAと同じ対象）")
    variance_decomposition(df, "area_group", "station_distance", "全area_group（本番モデルと同じ対象）")
    print()

    # --- 1. 疑似反復の確認: room数 vs building数 ---
    print("=== 1. 町別 room数 / building数（疑似反復の確認） ===")
    summary = (
        df_top.groupby("area_group")
        .agg(n_rooms=("room_id", "count"), n_buildings=("building_id", "nunique"))
        .loc[top_towns]
    )
    summary["rooms_per_building"] = (summary["n_rooms"] / summary["n_buildings"]).round(2)
    print(summary.to_string())
    print()

    # --- 1b. 各町内での station_distance と liv_area の相関（交絡の直接確認） ---
    print("=== 1b. 町別 corr(station_distance, liv_area)（Hirooで正なら交絡説を支持） ===")
    for t in top_towns:
        sub = df_top[df_top["area_group"] == t]
        corr = sub["station_distance"].corr(sub["liv_area"])
        print(f"  {t}: corr={corr:+.3f} (n={len(sub)})")
    print()

    # --- 2. 交互作用の共同検定: liv_area追加前後 ---
    print("=== 2. station_distance x C(area_group) 交互作用の共同検定（building単位クラスターSE） ===")

    formula_no_area = "log_price ~ station_distance * C(area_group)"
    formula_with_area = "log_price ~ station_distance * C(area_group) + np.log(liv_area)"
    formula_rent_per_m2 = "log_rent_per_m2 ~ station_distance * C(area_group)"

    for label, formula in [
        ("liv_area無し（生のlog_price）", formula_no_area),
        ("liv_area追加後（log_price + np.log(liv_area)）", formula_with_area),
        ("目的変数を平米単価に変更（log_rent_per_m2）", formula_rent_per_m2),
    ]:
        model = smf.ols(formula, data=df_top).fit(
            cov_type="cluster", cov_kwds=cluster_kwds(df_top)
        )
        interaction_terms = [p for p in model.params.index if p.startswith("station_distance:")]
        print(f"  [{label}]")
        if interaction_terms:
            wald = model.wald_test_terms(skip_single=False)
            # station_distance:C(area_group) の行を探す（statsmodelsのバージョンにより
            # 列名がF/P>Fだったりchi2/P>chi2だったりするため、列名を決め打ちしない）
            combined_name = [n for n in wald.table.index if "station_distance" in n and ":" in n]
            if combined_name:
                row = wald.table.loc[combined_name[0]]
                stat_col = "F" if "F" in row.index else ("chi2" if "chi2" in row.index else None)
                p_col = "P>F" if "P>F" in row.index else ("P>chi2" if "P>chi2" in row.index else None)
                if stat_col and p_col:
                    print(f"    交互作用項 共同検定（{stat_col}）: {stat_col}={row[stat_col]:.3f}  p={row[p_col]:.4f}")
                else:
                    print(f"    交互作用項 共同検定の生データ: {row.to_dict()}")
            else:
                print(f"    交互作用項の共同検定行が見つからず。wald.table全体:\n{wald.table}")
        else:
            print("    交互作用項なし（station_distanceのみのモデル）")
        print()

    # --- 3. 町別の駅徒歩スロープ（平米単価ベース、クラスターSE） ---
    print("=== 3. 町別 station_distance 係数（目的変数=log_rent_per_m2, building単位クラスターSE） ===")
    print("     ※ 各町を個別に回帰。町内でのbuilding数が少ないとクラスターSEの信頼性自体が低い点に注意。")
    for t in top_towns:
        sub = df_top[df_top["area_group"] == t]
        n_clusters = sub["building_id"].nunique()
        try:
            m = smf.ols("log_rent_per_m2 ~ station_distance", data=sub).fit(
                cov_type="cluster", cov_kwds={"groups": sub["building_id"]}
            )
            coef = m.params["station_distance"]
            p = m.pvalues["station_distance"]
            pct = (np.exp(coef) - 1) * 100
            print(f"  {t}: {pct:+.2f}%/分  p={p:.4f}  (n_rooms={len(sub)}, n_buildings={n_clusters})")
        except Exception as e:
            print(f"  {t}: 推定失敗 ({e})")
