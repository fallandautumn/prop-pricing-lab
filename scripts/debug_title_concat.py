"""
「Beverly Homes 神宮前 AP ビバリーホームズ神宮前AP」のように、英語名とカタカナ名が
連結されたような建物名がどれくらいあるかを数える。名寄せ処理（backfill_dedup_buildings.py）
の副作用の可能性がある。

簡易ヒューリスティック: タイトル内に英字とカタカナが両方含まれ、かつ長さが
20文字を超えるものを候補とする（正常な建物名は英字のみ or カタカナのみが多い）。

実行:
  python scripts/debug_title_concat.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text

from app.db.session import engine

if __name__ == "__main__":
    query = text("SELECT id, title FROM buildings WHERE title IS NOT NULL")
    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()

    has_latin = re.compile(r"[A-Za-z]")
    has_katakana = re.compile(r"[゠-ヿ]")

    candidates = [
        r for r in rows
        if len(r.title) > 20 and has_latin.search(r.title) and has_katakana.search(r.title)
    ]

    print(f"全building数: {len(rows)}")
    print(f"候補（英字+カタカナ混在・20文字超）: {len(candidates)}件\n")
    for r in candidates[:20]:
        print(f"  id={r.id}: {r.title!r}")
