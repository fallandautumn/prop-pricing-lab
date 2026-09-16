"""
docs/phase3_summary.mdで、price有りroom 2,998件のうちarea_group抽出後は
2,824件（約174件, 5.8%減）になっている食い違いを確認する。

area_group = df["address"].str.extract(r"(東京都.+?[区市].+?[一-龠]+)")
がNaNになる行がどんな住所なのか、母集団全体からNULLになった行が
系統的に偏っていないか（特定の町・building_typeに集中していないか）
を確認する。

実行:
  python scripts/check_area_group_nulls.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import engine
from app.analysis.matching import load_analysis_data

if __name__ == "__main__":
    df = load_analysis_data(engine)
    total = len(df)
    null_mask = df["area_group"].isna()
    n_null = null_mask.sum()

    print(f"全room数: {total}")
    print(f"area_group抽出失敗（NaN）: {n_null} ({n_null / total * 100:.1f}%)")
    print(f"area_group抽出成功: {total - n_null}")
    print()

    print("=== NaNになった住所のサンプル（最大20件） ===")
    for addr in df.loc[null_mask, "address"].head(20):
        print(f"  {addr!r}")
    print()

    print("=== NaNになった住所の building_type 内訳 ===")
    print(df.loc[null_mask, "building_type_cat"].value_counts().to_string())
    print()

    print("=== NaNになった行の住所が「東京都渋谷区」を含むかどうか ===")
    contains_shibuya = df.loc[null_mask, "address"].astype(str).str.contains("渋谷区")
    print(f"  「渋谷区」を含む: {contains_shibuya.sum()} / {n_null}")
    print(f"  含まない（他区・住所不備等の可能性）: {(~contains_shibuya).sum()} / {n_null}")
