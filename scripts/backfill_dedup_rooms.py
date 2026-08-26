"""
同一building内での重複掲載room（同一物理部屋の複数回投稿）を統合する。

背景: run_analysis.pyの割安トップ10に、同じ建物・同じ階・同じ専有面積・
同じ間取り・同じ価格の部屋が複数回登場する事例が見つかった
（例: ライオンズマンション初台が全く同じスペックで3件）。
実際にsuumo_room_id・urlを確認したところ、それぞれ別の掲載
（別の不動産会社経由と思われる）で、同一の物理的な部屋が重複して
スクレイピングされていることを確認した。

これはcheck_data_quality.pyの重複診断（COUNT(DISTINCT building_id) > 1を
要求）では検出できない盲点だった（building_idが同じなので対象外になる）。

このスクリプトは (building_id, floor, liv_area, floor_plan) を「同一物理部屋の
候補ファミリー」とみなし、以下のルールで統合する:
  - ファミリー内の価格が単一（またはNULL混在のみ）なら、ファミリー全体を
    1件に統合する。
  - ファミリー内に複数の異なる価格が混在する場合、価格ごとのサブグループに
    分割し、サブグループ内で2件以上一致するものだけを統合する
    （例: 245000円が2件・290000円が1件のファミリーなら、245000円の2件だけを
    安全に統合し、290000円の1件はそのまま残す。修正前はこの1件の存在だけで
    ファミリー全体の統合がブロックされ、テアトル神南で本来統合できたはずの
    完全一致ペアがトップ10に残るバグがあった）。
  - 価格がNULLの行は、複数価格が混在するファミリーではどのサブグループに
    属すか判別できないため統合対象に含めない（安全側）。
  - canonical: 価格が非NULLの行を優先。複数ある場合はmonthly_fee（price+admin_fee、
    admin_feeがNULLなら0扱い）が最小の行を採用する。同一物件でも取扱店舗によって
    管理費が異なるケースが確認されており（例: 同一price・admin_fee 15000円と
    8000円の2件）、実際に借りるなら合計額が最も安い条件を選ぶはずという考え方で
    代表行を選ぶ。さらに同点ならば最小room_idを採用。
  - 統合時は他の行を削除する（部屋データなので他テーブルへのFK参照はない）。

実行:
  python scripts/backfill_dedup_rooms.py           # dry-run（変更なし、対象を表示のみ）
  python scripts/backfill_dedup_rooms.py --apply   # 実際に統合を実行
"""
import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.db.models.room import Room


def _pick_canonical(group: list[Room]) -> tuple[Room, list[Room]]:
    priced = [r for r in group if r.price is not None]
    if priced:
        def _monthly_fee(r: Room) -> int:
            return r.price + (r.admin_fee or 0)

        min_fee = min(_monthly_fee(r) for r in priced)
        cheapest = [r for r in priced if _monthly_fee(r) == min_fee]
        canonical = min(cheapest, key=lambda r: r.id)
    else:
        canonical = min(group, key=lambda r: r.id)
    others = [r for r in group if r.id != canonical.id]
    return canonical, others


def find_merge_groups(db):
    rooms = (
        db.query(Room)
        .filter(Room.floor.isnot(None))
        .filter(Room.liv_area.isnot(None))
        .filter(Room.floor_plan.isnot(None))
        .all()
    )

    families: dict[tuple, list[Room]] = defaultdict(list)
    for r in rooms:
        key = (r.building_id, r.floor, r.liv_area, r.floor_plan)
        families[key].append(r)

    merge_plans: list[tuple[Room, list[Room]]] = []
    # (key, price_or_None, rows) — 統合できなかった残り
    skipped: list[tuple[tuple, int | None, list[Room]]] = []

    for key, family in families.items():
        if len(family) < 2:
            continue

        priced = [r for r in family if r.price is not None]
        none_priced = [r for r in family if r.price is None]
        distinct_prices = sorted({r.price for r in priced})

        if len(distinct_prices) <= 1:
            # 単一価格（またはNoneのみ混在） → ファミリー全体を統合
            canonical, others = _pick_canonical(family)
            merge_plans.append((canonical, others))
            continue

        # 複数価格が混在 → 価格ごとのサブグループに分けて判定
        for price_value in distinct_prices:
            subgroup = [r for r in priced if r.price == price_value]
            if len(subgroup) < 2:
                skipped.append((key, price_value, subgroup))
                continue
            canonical, others = _pick_canonical(subgroup)
            merge_plans.append((canonical, others))

        if none_priced:
            skipped.append((key, None, none_priced))

    return merge_plans, skipped


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        merge_plans, skipped = find_merge_groups(db)

        print(f"統合対象グループ: {len(merge_plans)}")
        total_deleted = 0
        for canonical, others in merge_plans:
            total_deleted += len(others)
            print(
                f"  building_id={canonical.building_id} canonical room_id={canonical.id} "
                f"(suumo_room_id={canonical.suumo_room_id}) "
                f"<- 削除対象 {[o.id for o in others]} "
                f"(price={canonical.price}, floor={canonical.floor}, "
                f"liv_area={canonical.liv_area}, floor_plan={canonical.floor_plan})"
            )

        print(f"\n削除対象room数の合計: {total_deleted}")
        print(f"\n統合できず残った行（単独価格 or 判別不能なNone）: {len(skipped)}")
        for key, price_value, rows in skipped[:15]:
            print(
                f"  building_id/floor/liv_area/floor_plan={key} "
                f"price={price_value}: room_ids={[r.id for r in rows]}"
            )

        if not apply:
            print("\n(dry-run。実際に統合するには --apply を付けて再実行してください)")
            return

        for canonical, others in merge_plans:
            for o in others:
                db.delete(o)
        db.commit()
        print(f"\n統合完了: {len(merge_plans)}グループ、{total_deleted}件のroomを削除しました。")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="実際にDBを変更する（省略時はdry-run）")
    args = parser.parse_args()
    main(apply=args.apply)
