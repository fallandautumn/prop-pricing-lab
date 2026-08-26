"""
指定区のbuilding/room行を削除するスクリプト（新宿区撤退用）。

背景: CEMのarea_groupは町名の完全一致でマッチングするため、区をまたいで
ストラータムが共有されることはない。新宿区を追加してもCEMのマッチ率
改善には寄与せず、新しい閑散としたストラータムが増えるだけだった。
渋谷区の密度を上げる方が本質的な対処のため、新宿区のデータを削除する。

Room.building_id には ON DELETE CASCADE が設定されていないため、
先にroomsを削除してからbuildingsを削除する（FK制約違反を避けるため）。

実行:
  python scripts/delete_ward.py --ward 新宿区            # dry-run（件数表示のみ）
  python scripts/delete_ward.py --ward 新宿区 --apply    # 実際に削除する
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.db.models.building import Building
from app.db.models.room import Room


def main(ward: str, apply: bool) -> None:
    db = SessionLocal()
    try:
        pattern = f"東京都{ward}%"
        building_ids = [
            b.id for b in db.query(Building.id).filter(Building.address.like(pattern)).all()
        ]
        n_rooms = db.query(Room).filter(Room.building_id.in_(building_ids)).count() if building_ids else 0

        print(f"対象: {ward} building={len(building_ids)}件 / room={n_rooms}件")

        if not apply:
            print("(dry-run。実際に削除するには --apply を付けて再実行してください)")
            return

        if building_ids:
            db.query(Room).filter(Room.building_id.in_(building_ids)).delete(synchronize_session=False)
            db.query(Building).filter(Building.id.in_(building_ids)).delete(synchronize_session=False)
            db.commit()

        print(f"削除完了: building={len(building_ids)}件 / room={n_rooms}件")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ward", required=True, help="削除対象の区名（例: 新宿区）")
    parser.add_argument("--apply", action="store_true", help="実際にDBを変更する（省略時はdry-run）")
    args = parser.parse_args()
    main(ward=args.ward, apply=args.apply)
