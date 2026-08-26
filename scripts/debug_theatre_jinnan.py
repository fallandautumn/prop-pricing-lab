"""
「テアトル神南」が割安トップ10で完全一致のまま重複している原因を調査する。
room単位の統合はbuilding_idごとにグループ化しているため、もし同名の建物が
複数のbuilding_idに分裂したまま残っていれば、room統合の対象外になる。

実行:
  python scripts/debug_theatre_jinnan.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text

from app.db.session import engine

if __name__ == "__main__":
    query = text("""
        SELECT b.id AS building_id, b.title, b.address, b.total_floors, b.age,
               r.id AS room_id, r.suumo_room_id, r.price, r.floor, r.liv_area,
               r.floor_plan, r.url, r.scraped_at
        FROM rooms r
        JOIN buildings b ON r.building_id = b.id
        WHERE b.title = 'テアトル神南'
        ORDER BY r.floor, r.price
    """)
    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()

    building_ids = set()
    for row in rows:
        building_ids.add(row.building_id)
        print(
            f"building_id={row.building_id} address={row.address!r} "
            f"total_floors={row.total_floors} age={row.age} "
            f"room_id={row.room_id} suumo_room_id={row.suumo_room_id} "
            f"price={row.price} floor={row.floor} liv_area={row.liv_area} "
            f"floor_plan={row.floor_plan}"
        )
        print(f"    url={row.url}  scraped_at={row.scraped_at}")

    print(f"\nユニークbuilding_id数: {len(building_ids)} -> {building_ids}")
