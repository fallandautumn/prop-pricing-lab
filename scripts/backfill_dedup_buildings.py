"""
既存DBの重複building行を統合するバックフィルスクリプト。

背景: extract_building_fields() のh1取得は、一部のSuumoページ（主に
建物名が未確定・非公開の新築物件など）で「路線 駅名 階建 築年数」という
自動生成の要約文を拾ってしまう(generic title)。この要約文は表示される
最寄り駅がlistingごとに揺れるため (title, address) の名寄せキーとして
機能せず、同じ物理的建物が複数のbuilding行に分裂して登録されていた。
（scraper側の本体修正は app/scraper/building.py の
is_generic_title / normalize_roman_suffix と scripts/run_scraper.py の
upsert_building フォールバック方式を参照）

このスクリプトは既存データに対して同じロジックを事後適用する:

1. (address, total_floors, age) が一致するbuilding群を再グループ化する。
2. グループ内の「非generic title」を集める。ローマ数字違い
   （II/2等）は事前に正規化し、さらに互いに部分文字列関係にある場合
   （マーケティング文言の前後付与によるものと推定）は同一名とみなす。
3. 上記を経てもなお異なる非generic titleが複数残る場合は「曖昧」として
   自動統合せずスキップし、一覧表示する（偶然スペックが一致した別の
   建物である可能性があるため、安全側に倒す）。
4. それ以外は1つのbuilding行に統合: 最短の非generic titleを持つ行を
   canonicalとし、他の行のroomsをcanonicalに付け替えて削除する。

実行:
  python scripts/backfill_dedup_buildings.py           # dry-run（変更なし、対象を表示のみ）
  python scripts/backfill_dedup_buildings.py --apply   # 実際に統合を実行
"""
import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from app.db.session import SessionLocal
from app.db.models.building import Building
from app.db.models.room import Room
from app.scraper.building import is_generic_title, normalize_roman_suffix


def _proper_titles(group: list[Building]) -> list[str]:
    """グループ内の非generic titleを、ローマ数字正規化した上で重複除去して返す。"""
    seen = []
    for b in group:
        if not b.title or is_generic_title(b.title):
            continue
        t = normalize_roman_suffix(b.title)
        if t not in seen:
            seen.append(t)
    return seen


def _all_substring_related(titles: list[str]) -> bool:
    """
    全てのtitleが、最短のtitleを含む関係にあるか（マーケティング文言の前後付与か）を判定する。
    スペースの有無だけの表記ゆれ（例: "PASEO 笹塚II" / "PASEO笹塚II"）を
    同一視するため、比較時のみ空白を除去する（canonical titleの表示自体は元の表記を保つ）。
    """
    if len(titles) <= 1:
        return True
    collapsed = [t.replace(" ", "").replace("　", "") for t in titles]
    shortest = min(collapsed, key=len)
    return all(shortest in t for t in collapsed)


def find_merge_groups(db):
    buildings = (
        db.query(Building)
        .filter(Building.address.isnot(None))
        .filter(Building.total_floors.isnot(None))
        .filter(Building.age.isnot(None))
        .all()
    )
    groups: dict[tuple, list[Building]] = defaultdict(list)
    for b in buildings:
        key = (b.address, b.total_floors, b.age)
        groups[key].append(b)

    merge_plans = []
    skipped_ambiguous = []
    for key, group in groups.items():
        if len(group) < 2:
            continue

        proper_titles = _proper_titles(group)
        if len(proper_titles) > 1 and not _all_substring_related(proper_titles):
            skipped_ambiguous.append((key, group))
            continue

        canonical_title = min(proper_titles, key=len) if proper_titles else None
        if canonical_title:
            canonical = next(
                (b for b in group if b.title and normalize_roman_suffix(b.title) == canonical_title),
                group[0],
            )
        else:
            canonical = group[0]  # 全員generic title -> 便宜上先頭を採用

        others = [b for b in group if b.id != canonical.id]
        merge_plans.append((canonical, others))

    return merge_plans, skipped_ambiguous


def main(apply: bool):
    db = SessionLocal()
    try:
        merge_plans, skipped = find_merge_groups(db)

        print(f"統合対象グループ: {len(merge_plans)}")
        total_rooms_moved = 0
        for canonical, others in merge_plans:
            n_rooms = db.query(Room).filter(Room.building_id.in_([o.id for o in others])).count()
            total_rooms_moved += n_rooms
            print(
                f"  canonical: id={canonical.id} title={canonical.title!r} "
                f"<- merge {[o.id for o in others]} (titles={[o.title for o in others]}) "
                f"[{n_rooms}部屋を付け替え]"
            )

        print(f"\n付け替え対象部屋数の合計: {total_rooms_moved}")
        print(f"\n曖昧なため統合をスキップしたグループ（非generic titleが複数種類・部分文字列関係でもない）: {len(skipped)}")
        for key, group in skipped[:15]:
            print(f"  address/floors/age={key}: titles={[b.title for b in group]}")

        if not apply:
            print("\n(dry-run。実際に統合するには --apply を付けて再実行してください)")
            return

        for canonical, others in merge_plans:
            other_ids = [o.id for o in others]
            db.query(Room).filter(Room.building_id.in_(other_ids)).update(
                {Room.building_id: canonical.id}, synchronize_session=False
            )
            for o in others:
                db.delete(o)
        db.commit()
        print(f"\n統合完了: {len(merge_plans)}グループを統合、{total_rooms_moved}部屋を付け替えました。")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="実際にDBを変更する（省略時はdry-run）")
    args = parser.parse_args()
    main(apply=args.apply)
