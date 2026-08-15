"""
部屋ページのHTML構造を診断するスクリプト。面積(liv_area)欠損の原因調査用。

使い方:
    docker compose run --rm api python scripts/debug_room.py <room_url>
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scraper.http import get_soup

url = sys.argv[1] if len(sys.argv) > 1 else input("部屋URL: ").strip()

soup = get_soup(url)

print("\n" + "=" * 60)
print("【全 tr の th/td ペア】")
print("=" * 60)
for i, row in enumerate(soup.select("tr")):
    th = row.select_one("th")
    td = row.select_one("td")
    if th and td:
        key = th.get_text(strip=True)
        val = td.get_text(strip=True)
        marker = " <== 面積を含む" if "面積" in key else ""
        print(f"  [{i}] {key!r}: {val!r}{marker}")
