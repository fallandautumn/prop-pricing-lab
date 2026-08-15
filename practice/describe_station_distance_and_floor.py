"""
station_distance（駅徒歩分）と floor（部屋の階数）の記述統計量

rooms x buildings を結合し、price IS NOT NULL のデータに対して
station_distance / floor それぞれの N・平均・標準偏差・最大・最小を出力する。
欠損値は列ごとに除外して計算する（N列で欠損の有無が分かる）。

実行:
  docker compose run --rm api python practice/describe_station_distance_and_floor.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import pandas as pd

from app.db.session import engine

JOIN_QUERY = """
SELECT
    r.floor,
    b.station_distance
FROM rooms r
JOIN buildings b ON b.id = r.building_id
WHERE r.price IS NOT NULL
"""


def load_df() -> pd.DataFrame:
    df = pd.read_sql(JOIN_QUERY, engine)
    if df.empty:
        raise SystemExit("price IS NOT NULL のデータが0件です。スクレイピング/DB接続を確認してください。")
    return df


def describe_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    stats = df[columns].agg(["count", "mean", "std", "max", "min"]).T
    stats = stats.rename(columns={"count": "N"})
    stats["N"] = stats["N"].astype(int)
    return stats.round(2)


def main():
    df = load_df()
    print(f"=== 対象データ: {len(df)}部屋（price IS NOT NULL） ===")

    stats = describe_columns(df, ["station_distance", "floor"])
    print("\n--- station_distance（駅徒歩分）/ floor（部屋の階数）の記述統計量 ---")
    print(stats.to_string())


if __name__ == "__main__":
    main()
