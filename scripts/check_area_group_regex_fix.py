"""
app/analysis/matching.py の area_group 正規表現修正（2026-09）の効果を確認する。

計3世代の正規表現を比較する:
  V1（元の実装）: r"(東京都.+?[区市].+?[一-龠]+)"
    -> 町名が漢字1文字（例: "渋谷区東４"）の住所でNaNになっていた（174件）。
  V2（1回目の修正、リグレッションあり）: r"(東京都[一-龠]+?[区市][一-龠]+)"
    -> V1のバグは直ったが、町名部分を[一-龠]（漢字限定）にしたことで
       「々」「ヶ」を含む町名（代々木・幡ヶ谷など）が途中で切り詰められる
       新バグを生んだ。
  V3（最終修正、現在の本番コード）: r"(東京都.+?[区市]\\D+)"
    -> 町名部分を「数字以外」で捉えることで、V1・V2どちらのバグも解消。

実行:
  python scripts/check_area_group_regex_fix.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import engine
from app.analysis.matching import load_analysis_data

V1_PATTERN = r"(東京都.+?[区市].+?[一-龠]+)"
V2_PATTERN = r"(東京都[一-龠]+?[区市][一-龠]+)"
V3_PATTERN = r"(東京都.+?[区市]\D+)"  # 本番（app/analysis/matching.py）と同一

if __name__ == "__main__":
    df = load_analysis_data(engine)  # V3（現在の本番コード）のarea_groupが入っている

    total = len(df)
    n_null_v3 = df["area_group"].isna().sum()
    n_null_v1 = df["address"].str.extract(V1_PATTERN)[0].isna().sum()
    n_null_v2 = df["address"].str.extract(V2_PATTERN)[0].isna().sum()

    print(f"全room数: {total}")
    print(f"V1のNaN件数: {n_null_v1}")
    print(f"V2のNaN件数: {n_null_v2}")
    print(f"V3（本番）のNaN件数: {n_null_v3}")
    print()

    print("=== サンプルテスト ===")
    test_addrs = [
        "東京都渋谷区東4",
        "東京都渋谷区東2-1-1",
        "東京都渋谷区代々木３－１－１",
        "東京都渋谷区幡ヶ谷１－２－３",
        "東京都渋谷区笹塚1丁目",
        "東京都渋谷区松濤2",
    ]
    for addr in test_addrs:
        v1_match = re.search(V1_PATTERN, addr)
        v2_match = re.search(V2_PATTERN, addr)
        v3_match = re.search(V3_PATTERN, addr)
        print(f"  {addr!r}")
        print(f"    V1: {v1_match.group(1) if v1_match else 'NaN(マッチ失敗)'}")
        print(f"    V2: {v2_match.group(1) if v2_match else 'NaN(マッチ失敗)'}")
        print(f"    V3: {v3_match.group(1) if v3_match else 'NaN(マッチ失敗)'}")

    print()
    print("=== V1で失敗しV3で救済された町名の内訳（上位10） ===")
    v1_area_group = df["address"].str.extract(V1_PATTERN)[0]
    rescued = df.loc[v1_area_group.isna() & df["area_group"].notna(), "area_group"]
    print(rescued.value_counts().head(10).to_string())

    print()
    print("=== V2とV3で結果が異なる町名（々・ヶ等を含む町名の影響確認） ===")
    v2_area_group = df["address"].str.extract(V2_PATTERN)[0]
    diff_mask = (v2_area_group != df["area_group"]) & df["area_group"].notna()
    if diff_mask.sum() == 0:
        print("  差分なし")
    else:
        diff_df = df.loc[diff_mask, ["address", "area_group"]].copy()
        diff_df["v2_area_group"] = v2_area_group.loc[diff_mask]
        print(f"  差分件数: {diff_mask.sum()}")
        print(diff_df["area_group"].value_counts().to_string())
