"""
割安トップ10に出現した重複建物（イースタンホームズ猿楽、ライオンズマンション初台、
エコーハイツ等）を実際に調査する診断スクリプト。

同一building内で、価格・階・専有面積・間取りが完全一致するroomが複数ある
場合、それが「本当に別々の部屋（たまたま同スペック）」なのか「同一物件の
重複掲載（別suumo_room_id・別url）」なのかをurlを突き合わせて確認する。

実行:
  python scripts/debug_duplicate_rooms.py
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
        SELECT b.id AS building_id, b.title, b.address, b.total_units,
               r.id AS room_id, r.suumo_room_id, r.price, r.floor, r.liv_area,
               r.floor_plan, r.url, r.scraped_at
        FROM rooms r
        JOIN buildings b ON r.building_id = b.id
        WHERE b.title IN ('イースタンホームズ猿楽', 'ライオンズマンション初台', 'エコーハイツ')
        ORDER BY b.title, r.price, r.floor
    """)
    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()

    for row in rows:
        print(
            f"building={row.title}(id={row.building_id}, 総戸数={row.total_units}) "
            f"room_id={row.room_id} suumo_room_id={row.suumo_room_id} "
            f"price={row.price} floor={row.floor} liv_area={row.liv_area} "
            f"floor_plan={row.floor_plan}"
        )
        print(f"    url={row.url}")
        print(f"    scraped_at={row.scraped_at}")
