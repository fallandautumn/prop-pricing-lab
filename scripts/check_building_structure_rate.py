"""
building_structureの取得率を確認する。

実行:
  python scripts/check_building_structure_rate.py
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
        SELECT
            COUNT(*) AS total,
            COUNT(building_structure) AS with_structure,
            COUNT(*) FILTER (WHERE building_structure IS NULL OR building_structure = '') AS missing
        FROM buildings
    """)
    with engine.connect() as conn:
        row = conn.execute(query).fetchone()

    rate = row.with_structure / row.total * 100
    print(f"全building数: {row.total}")
    print(f"building_structure取得済み: {row.with_structure} ({rate:.1f}%)")
    print(f"欠損: {row.missing}")

    # 内訳（RC/SRC/木造 等）
    dist_query = text("""
        SELECT building_structure, COUNT(*) AS n
        FROM buildings
        WHERE building_structure IS NOT NULL AND building_structure != ''
        GROUP BY building_structure
        ORDER BY n DESC
    """)
    with engine.connect() as conn:
        rows = conn.execute(dist_query).fetchall()

    print("\n内訳:")
    for r in rows:
        print(f"  {r.building_structure}: {r.n}")
