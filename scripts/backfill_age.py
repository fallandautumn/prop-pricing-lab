"""
age が実は西暦（建築年）のまま保存されていた行を修正するバックフィルスクリプト。
building.py の _parse_age() 修正に合わせて、既存DBの値も補正する。

実行:
  python scripts/backfill_age.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.db.session import engine


def main():
    with engine.begin() as conn:
        # 修正前の確認
        rows = conn.execute(
            text("SELECT id, title, age FROM buildings WHERE age > 200 ORDER BY age")
        ).fetchall()
        print(f"=== 修正対象: {len(rows)}件 ===")
        for r in rows[:20]:
            print(f"  id={r.id} title={r.title!r} age={r.age}")
        if len(rows) > 20:
            print(f"  ...他{len(rows) - 20}件")

        if not rows:
            print("修正対象なし。終了します。")
            return

        # 実修正: 現在年 - 建築年 に変換
        result = conn.execute(
            text(
                "UPDATE buildings SET age = EXTRACT(YEAR FROM CURRENT_DATE)::int - age "
                "WHERE age > 200"
            )
        )
        print(f"\n=== {result.rowcount}件を修正しました ===")

        # 修正後の分布確認
        stats = conn.execute(
            text("SELECT min(age), max(age), avg(age)::numeric(10,1) FROM buildings WHERE age IS NOT NULL")
        ).one()
        print(f"修正後の分布: min={stats[0]} max={stats[1]} avg={stats[2]}")


if __name__ == "__main__":
    main()
