"""データ品質診断スクリプト（重複掲載候補・フィールド欠損率）。

新宿区スクレイピングでサンプルを増やす前に、既存データの品質問題の
規模を把握するための診断。まだ自動修正は行わない（現状把握のみ）。

実行:
  python scripts/check_data_quality.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

import pandas as pd
from sqlalchemy import text

from app.db.session import engine


def check_duplicate_candidates() -> pd.DataFrame:
    """異なる building_id だが 住所+階+専有面積+間取り が完全一致する部屋を重複掲載候補として検出する。

    注意: 同一建物内で標準化された間取りタイプ（例: 1Kが複数室同スペック）が
    偶然一致するケースも混ざりうるため、ここでは「候補」の件数を把握するのみで
    自動マージはしない。building_id が異なる、かつ address が完全一致している
    時点で「別建物として登録されているが実は同じ建物」の疑いが強い。
    """
    query = text("""
        SELECT b.address, r.floor, r.liv_area, r.floor_plan,
               COUNT(DISTINCT r.building_id) AS n_buildings,
               COUNT(*) AS n_rooms,
               STRING_AGG(DISTINCT b.title, ' / ') AS titles,
               STRING_AGG(DISTINCT r.price::text, ' / ') AS prices
        FROM rooms r
        JOIN buildings b ON r.building_id = b.id
        WHERE r.floor IS NOT NULL AND r.liv_area IS NOT NULL AND r.floor_plan IS NOT NULL
        GROUP BY b.address, r.floor, r.liv_area, r.floor_plan
        HAVING COUNT(DISTINCT r.building_id) > 1
        ORDER BY n_rooms DESC
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    print(f"重複掲載候補グループ数: {len(df)}")
    print(f"関与する部屋数の合計: {int(df['n_rooms'].sum()) if len(df) else 0}")
    if len(df):
        print("\n--- 上位20件（部屋数が多い順） ---")
        print(df.head(20).to_string(index=False))
    return df


def check_field_fill_rates() -> None:
    query = text("""
        SELECT
          COUNT(*) AS n_buildings,
          COUNT(building_structure) AS n_structure,
          COUNT(total_floors) AS n_total_floors,
          COUNT(age) AS n_age,
          COUNT(station_distance) AS n_station_distance,
          COUNT(brand_score) AS n_brand_score,
          COUNT(total_units) AS n_total_units
        FROM buildings
    """)
    with engine.connect() as conn:
        row = pd.read_sql(query, conn).iloc[0]

    n = row["n_buildings"]
    print(f"\n--- buildings フィールド充足率 (N={n}) ---")
    for col, label in [
        ("n_structure", "building_structure"),
        ("n_total_floors", "total_floors"),
        ("n_age", "age"),
        ("n_station_distance", "station_distance"),
        ("n_brand_score", "brand_score(LLM)"),
        ("n_total_units", "total_units(新規)"),
    ]:
        cnt = row[col]
        print(f"  {label:20s}: {cnt}/{n} ({cnt / n:.1%})")

    query_rooms = text("""
        SELECT
          COUNT(*) AS n_rooms,
          COUNT(liv_area) AS n_liv_area,
          COUNT(floor) AS n_floor,
          COUNT(floor_plan) AS n_floor_plan,
          COUNT(estimated_price) AS n_estimated_price,
          COUNT(orientation) AS n_orientation,
          COUNT(move_in_date) AS n_move_in_date,
          COUNT(url) AS n_url
        FROM rooms
    """)
    with engine.connect() as conn:
        row_r = pd.read_sql(query_rooms, conn).iloc[0]
    n_r = row_r["n_rooms"]
    print(f"\n--- rooms フィールド充足率 (N={n_r}) ---")
    for col, label in [
        ("n_liv_area", "liv_area"),
        ("n_floor", "floor"),
        ("n_floor_plan", "floor_plan"),
        ("n_estimated_price", "estimated_price(スコア計算済み)"),
        ("n_orientation", "orientation(新規)"),
        ("n_move_in_date", "move_in_date(新規)"),
        ("n_url", "url(新規)"),
    ]:
        cnt = row_r[col]
        print(f"  {label:28s}: {cnt}/{n_r} ({cnt / n_r:.1%})")

    if row["n_total_units"] == 0:
        print("\n  [注意] total_unitsが全件None。抽出ロジック側の不具合の可能性があるため要確認。")


if __name__ == "__main__":
    print("=== 重複掲載候補の診断 ===")
    check_duplicate_candidates()
    check_field_fill_rates()
