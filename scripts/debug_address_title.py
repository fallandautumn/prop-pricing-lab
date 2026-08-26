"""
titleが建物名ではなく住所そのものになっている建物を検出する診断スクリプト。

check_llm_scores.pyの出力で「東京都渋谷区広尾1」のようなtitleを発見した。
これは既知の「駅名要約文」パターン（is_generic_title）とは別の、3つ目の
h1抽出失敗パターンの可能性がある。規模と実例を確認する。

実行:
  python scripts/debug_address_title.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text

from app.db.session import engine

if __name__ == "__main__":
    query = text(r"""
        SELECT b.id, b.title, b.address, r.suumo_room_id
        FROM buildings b
        JOIN rooms r ON r.building_id = b.id
        WHERE b.title ~ '^東京都.+[区市]'
        ORDER BY b.id
    """)
    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()

    print(f"該当building（重複roomは除かず表示）: {len(rows)}件（表示上限20）")
    seen_building = set()
    count_building = 0
    for row in rows:
        if row.id not in seen_building:
            seen_building.add(row.id)
            count_building += 1
    print(f"うちユニークなbuilding数: {count_building}")

    for row in rows[:20]:
        print(f"  building_id={row.id} title={row.title!r} address={row.address!r}")
        print(f"    -> https://suumo.jp/chintai/{row.suumo_room_id}/")
