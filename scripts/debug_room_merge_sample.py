"""
backfill_dedup_rooms.pyの統合候補グループが「本当に同一物件の重複掲載」なのか
「たまたま同スペック・同家賃の別の部屋」なのかを、サンプル抽出して目視検証する。

1898件という統合対象件数は、(floor, liv_area, floor_plan, price)だけでは
判別力が不足している可能性を示唆する（特にtotal_unitsが大きい建物では、
同じ間取りタイプの部屋が複数戸存在し、賃料設定も同じになるケースが
普通にあり得るため）。

total_unitsで層化抽出し、各グループの実urlを表示して個別に確認できるようにする。

実行:
  python scripts/debug_room_merge_sample.py
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.db.models.room import Room
from app.db.models.building import Building


def main() -> None:
    db = SessionLocal()
    try:
        rooms = (
            db.query(Room, Building)
            .join(Building, Room.building_id == Building.id)
            .filter(Room.floor.isnot(None))
            .filter(Room.liv_area.isnot(None))
            .filter(Room.floor_plan.isnot(None))
            .all()
        )

        groups: dict[tuple, list] = defaultdict(list)
        for r, b in rooms:
            key = (r.building_id, r.floor, r.liv_area, r.floor_plan)
            groups[key].append((r, b))

        # 統合候補（価格が単一 or NULL混在のみ）だけに絞る
        candidates = []
        for key, group in groups.items():
            if len(group) < 2:
                continue
            prices = {r.price for r, _ in group if r.price is not None}
            if len(prices) > 1:
                continue
            candidates.append((key, group))

        # total_unitsで層化: 小さい(<=10)/中(11-30)/大(31+)/不明(NULL)
        def bucket(total_units):
            if total_units is None:
                return "不明"
            if total_units <= 10:
                return "小(<=10)"
            if total_units <= 30:
                return "中(11-30)"
            return "大(31+)"

        buckets: dict[str, list] = defaultdict(list)
        for key, group in candidates:
            tu = group[0][1].total_units
            buckets[bucket(tu)].append((key, group))

        print(f"統合候補グループ総数: {len(candidates)}")
        for b, items in buckets.items():
            print(f"  {b}: {len(items)}グループ")

        print("\n=== サンプル（各層から最大4件） ===\n")
        for b, items in buckets.items():
            print(f"--- {b} ---")
            for key, group in items[:4]:
                building_id, floor, liv_area, floor_plan = key
                b_row = group[0][1]
                print(
                    f"building_id={building_id} title={b_row.title!r} "
                    f"total_units={b_row.total_units} "
                    f"floor={floor} liv_area={liv_area} floor_plan={floor_plan}"
                )
                for r, _ in group:
                    print(
                        f"    room_id={r.id} suumo_room_id={r.suumo_room_id} "
                        f"price={r.price} scraped_at={r.scraped_at}"
                    )
                    print(f"      url={r.url}")
            print()

    finally:
        db.close()


if __name__ == "__main__":
    main()
