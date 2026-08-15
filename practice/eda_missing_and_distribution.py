"""
rooms x buildings 結合データの EDA（欠損状況・部屋数分布）

check_data.sql の 1〜3 を、rooms.price IS NOT NULL で絞った
rooms x buildings 結合データに対して実行し、集計結果をターミナルに
度数分布表として出力する。--png 指定時は同内容を画像でも保存する。

tation_distance（駅徒歩分）と floor（部屋の階数）の記述統計量
rooms x buildings を結合し、price IS NOT NULL のデータに対して
station_distance / floor それぞれの N・平均・標準偏差・最大・最小を出力する。
欠損値は列ごとに除外して計算する（N列で欠損の有無が分かる）。

実行:
  docker compose run --rm api python scripts/eda_missing_and_distribution.py

出力:
  - 1. buildings 欠損状況（対象: price非NULLのroomを持つ建物のみ）
  - 2. rooms（price有り）欠損状況
  - 3. 建物あたりの部屋数分布
  - 4. station_distance / floor の記述統計量
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import pandas as pd

from app.db.session import engine

FIGURES_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "figures")

JOIN_QUERY = """
SELECT
    r.id AS room_id,
    r.building_id,
    r.price,
    r.floor,
    r.liv_area,
    r.floor_plan,
    b.station_distance,
    b.age,
    b.total_floors,
    b.building_structure
FROM rooms r
JOIN buildings b ON b.id = r.building_id
WHERE r.price IS NOT NULL
"""


def load_joined_df() -> pd.DataFrame:
    df = pd.read_sql(JOIN_QUERY, engine)
    if df.empty:
        raise SystemExit("price IS NOT NULL のデータが0件です。スクレイピング/DB接続を確認してください。")
    return df


def missing_summary(df: pd.DataFrame, columns: list[str], total_label: str) -> pd.DataFrame:
    total = len(df)
    rows = []
    for col in columns:
        non_null = df[col].notna().sum()
        rows.append({
            "column": col,
            "total": total,
            "non_null": non_null,
            "missing": total - non_null,
            "missing_rate": round((total - non_null) / total, 3) if total else float("nan"),
        })
    out = pd.DataFrame(rows).set_index("column")
    print(f"\n--- {total_label} (N={total}) ---")
    print(out.to_string())
    return out


def print_ascii_freq(series_counts: pd.Series, label: str, bar_char: str = "#", width: int = 40) -> None:
    """整数インデックス -> 度数 の Series をターミナルに棒グラフ風に出力する"""
    print(f"\n--- {label} ---")
    if series_counts.empty:
        print("  (データなし)")
        return
    max_count = series_counts.max()
    for idx, count in series_counts.items():
        bar_len = max(1, round(count / max_count * width)) if max_count else 0
        bar = bar_char * bar_len
        print(f"  {idx:>3}部屋 | {bar:<{width}} {count}棟")


def analyze_buildings_missing(df: pd.DataFrame) -> pd.DataFrame:
    """1. buildings 欠損状況（対象: price非NULLのroomを持つ建物のみ、重複排除）"""
    b = df.drop_duplicates(subset="building_id")
    cols = ["station_distance", "age", "total_floors", "building_structure"]
    return missing_summary(b, cols, "1. buildings 欠損状況（price非NULL roomを持つ建物のみ）")


def analyze_rooms_missing(df: pd.DataFrame) -> pd.DataFrame:
    """2. rooms（price有り）欠損状況"""
    cols = ["floor", "liv_area", "floor_plan"]
    return missing_summary(df, cols, "2. rooms（price有り）欠損状況")


def analyze_room_count_distribution(df: pd.DataFrame) -> pd.Series:
    """3. 建物あたりの部屋数分布"""
    room_counts = df.groupby("building_id")["room_id"].count()
    freq = room_counts.value_counts().sort_index()
    freq.index.name = "room_count"
    print_ascii_freq(freq, "3. 建物あたりの部屋数分布")
    return freq


def save_png_charts(missing_buildings: pd.DataFrame, missing_rooms: pd.DataFrame, room_count_freq: pd.Series) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs(FIGURES_DIR, exist_ok=True)

    # 1 & 2: 欠損率の棒グラフ（日本語フォント未設定環境でも崩れないよう英語ラベルを使用）
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(missing_buildings.index, missing_buildings["missing_rate"], color="#4C72B0")
    ax.set_title("Buildings: missing rate (rooms with price only)")
    ax.set_ylabel("missing rate")
    ax.set_ylim(0, 1)
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    path1 = os.path.join(FIGURES_DIR, "01_buildings_missing_rate.png")
    fig.savefig(path1, dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(missing_rooms.index, missing_rooms["missing_rate"], color="#DD8452")
    ax.set_title("Rooms (price not null): missing rate")
    ax.set_ylabel("missing rate")
    ax.set_ylim(0, 1)
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    path2 = os.path.join(FIGURES_DIR, "02_rooms_missing_rate.png")
    fig.savefig(path2, dpi=150)
    plt.close(fig)

    # 3: 建物あたりの部屋数分布
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(room_count_freq.index.astype(str), room_count_freq.values, color="#55A868")
    ax.set_title("Rooms per building: distribution")
    ax.set_xlabel("room count")
    ax.set_ylabel("num buildings")
    plt.tight_layout()
    path3 = os.path.join(FIGURES_DIR, "03_room_count_distribution.png")
    fig.savefig(path3, dpi=150)
    plt.close(fig)

    print(f"\nPNG保存先: {os.path.abspath(FIGURES_DIR)}")
    for p in (path1, path2, path3):
        print(f"  - {os.path.basename(p)}")

def describe_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    stats = df[columns].agg(["count", "mean", "std", "max", "min"]).T
    stats = stats.rename(columns={"count": "N"})
    stats["N"] = stats["N"].astype(int)
    return stats.round(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--png", action="store_true", help="集計結果をPNG画像でも保存する（docs/figures/）")
    args = parser.parse_args()

    df = load_joined_df()
    print(f"=== 対象データ: {len(df)}部屋 / {df['building_id'].nunique()}棟（price IS NOT NULL） ===")

    missing_buildings = analyze_buildings_missing(df)
    missing_rooms = analyze_rooms_missing(df)
    room_count_freq = analyze_room_count_distribution(df)

    if args.png:
        try:
            save_png_charts(missing_buildings, missing_rooms, room_count_freq)
        except ImportError:
            print(
                "\n[警告] matplotlib が見つかりません。"
                " `pip install matplotlib` を requirements.txt に追加してから再実行してください。"
            )

    print(f"=== 対象データ: {len(df)}部屋（price IS NOT NULL） ===")
    
    stats = describe_columns(df, ["station_distance", "floor"])
    print("\n--- station_distance（駅徒歩分）/ floor（部屋の階数）の記述統計量 ---")
    print(stats.to_string())


if __name__ == "__main__":
    main()
