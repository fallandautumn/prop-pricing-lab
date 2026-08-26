"""
建物タイトルが「駅名+階建+築年数」のような要約文になってしまっている
（本来の建物名を取得できていない）ケースを診断するスクリプト。

DBから該当パターンのbuildingを探し、そこに紐づくroomのURLを再構築して
実際に取得し、h1タグの構造を出力する。extract_building_fields() の
h1セレクタ (soup.select_one("h1")) がどのケースで誤爆するかを特定するのが目的。

実行:
  python scripts/debug_title_bug.py [件数（デフォルト3）]
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from app.db.session import engine
from app.scraper.http import get_soup

# 「駅」「階建」「築」を全部含むtitleは、建物名ではなく要約文が
# 誤ってh1として取得された疑いが強い（今回発見したパターン）。
SUSPICIOUS_PATTERN = re.compile(r"駅.*階建.*築|築.*駅.*階建")


def find_suspicious_buildings(limit: int):
    query = text("""
        SELECT b.id, b.title, b.address, r.suumo_room_id
        FROM buildings b
        JOIN rooms r ON r.building_id = b.id
        WHERE b.title ~ '駅' AND b.title ~ '階建' AND b.title ~ '築'
        ORDER BY b.id
        LIMIT :limit
    """)
    with engine.connect() as conn:
        rows = conn.execute(query, {"limit": limit}).fetchall()
    return rows


def dump_h1_structure(url: str):
    print(f"\n  URL: {url}")
    try:
        soup = get_soup(url)
    except Exception as e:
        print(f"  取得失敗: {e}")
        return

    h1_tags = soup.select("h1")
    print(f"  h1タグ数: {len(h1_tags)}")
    for i, h1 in enumerate(h1_tags):
        print(f"    [{i}] class={h1.get('class')} text={h1.get_text(strip=True)[:80]!r}")

    print("  --- 建物名候補になりそうな他のセレクタ ---")
    for sel in [
        ".property_view_main-title",
        ".section_h1-header-title",
        ".bukken-name",
        ".property_view_main-emphasis",
        "h2",
    ]:
        tags = soup.select(sel)
        for t in tags[:2]:
            print(f"    {sel}: {t.get_text(strip=True)[:80]!r}")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    rows = find_suspicious_buildings(limit)
    print(f"該当building: {len(rows)}件（表示上限{limit}）")
    for row in rows:
        print(f"\nbuilding_id={row.id} title={row.title!r} address={row.address!r}")
        url = f"https://suumo.jp/chintai/{row.suumo_room_id}/"
        dump_h1_structure(url)
