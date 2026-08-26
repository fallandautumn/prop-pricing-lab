"""
「2000年以降築のマンションはほぼRCだから、building_structureは考慮しなくてよい」
という理屈が実データで成立するかを確認する。

実行:
  python scripts/check_structure_age_crosstab.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text

from app.db.session import engine

if __name__ == "__main__":
    with engine.connect() as conn:
        # building_type別のbuilding_structure分布
        print("=== building_type別 building_structure分布 ===")
        rows = conn.execute(text("""
            SELECT building_type, building_structure, COUNT(*) AS n
            FROM buildings
            GROUP BY building_type, building_structure
            ORDER BY building_type, n DESC
        """)).fetchall()
        for r in rows:
            print(f"  {r.building_type or '(不明)':<10} {r.building_structure or '(欠損)':<10} {r.n}")

        # 築年数(age)別のRC率（2000年以降=築26年未満、2026年基準）
        print("\n=== 築年数バケット別のRC率 ===")
        rows = conn.execute(text("""
            SELECT
                CASE
                    WHEN age IS NULL THEN '不明'
                    WHEN age < 26 THEN '築26年未満(2000年以降築)'
                    ELSE '築26年以上(2000年より前)'
                END AS age_bucket,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE building_structure = 'RC') AS rc_count
            FROM buildings
            GROUP BY age_bucket
        """)).fetchall()
        for r in rows:
            rate = r.rc_count / r.total * 100 if r.total else 0
            print(f"  {r.age_bucket}: 全{r.total}件中RC={r.rc_count}件 ({rate:.1f}%)")

        # マンションのみに絞った場合
        print("\n=== building_type='マンション'のみ、築年数バケット別RC率 ===")
        rows = conn.execute(text("""
            SELECT
                CASE
                    WHEN age IS NULL THEN '不明'
                    WHEN age < 26 THEN '築26年未満(2000年以降築)'
                    ELSE '築26年以上(2000年より前)'
                END AS age_bucket,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE building_structure = 'RC') AS rc_count
            FROM buildings
            WHERE building_type = 'マンション'
            GROUP BY age_bucket
        """)).fetchall()
        for r in rows:
            rate = r.rc_count / r.total * 100 if r.total else 0
            print(f"  {r.age_bucket}: 全{r.total}件中RC={r.rc_count}件 ({rate:.1f}%)")
