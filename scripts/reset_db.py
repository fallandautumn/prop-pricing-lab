"""
buildings / rooms テーブルを完全にリセットする（データのみ削除、スキーマは維持）。

過去の設計世代（name+address dedup以前のロジックで入った行、掲載終了済みで
二度とスクレイピングされない行等）を一掃し、現行コードで一から取得し直す
ためのスクリプト。TRUNCATE ... RESTART IDENTITY CASCADE でIDも1から振り直す。

実行:
  python scripts/reset_db.py            # dry-run（件数表示のみ）
  python scripts/reset_db.py --apply    # 実際に全削除する
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text

from app.db.session import engine


def main(apply: bool) -> None:
    with engine.connect() as conn:
        n_buildings = conn.execute(text("SELECT count(*) FROM buildings")).scalar()
        n_rooms = conn.execute(text("SELECT count(*) FROM rooms")).scalar()

    print(f"現在: buildings={n_buildings}件 / rooms={n_rooms}件")

    if not apply:
        print("(dry-run。実際に削除するには --apply を付けて再実行してください)")
        return

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE rooms, buildings RESTART IDENTITY CASCADE"))

    print("削除完了: buildings/rooms を空にしました（IDも1から振り直し）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="実際にDBを変更する（省略時はdry-run）")
    args = parser.parse_args()
    main(apply=args.apply)
