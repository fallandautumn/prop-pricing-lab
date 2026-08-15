"""建物構造(RC/SRC/木造等)フィールドの所在を調査する。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.scraper.http import get_soup
from app.scraper.room import _iter_detail_pairs

url = sys.argv[1] if len(sys.argv) > 1 else input("部屋URL: ").strip()
soup = get_soup(url)

print("=== _iter_detail_pairs の全ペア ===")
for th, td in _iter_detail_pairs(soup):
    print(f"  {th.get_text(strip=True)!r}: {td.get_text(strip=True)!r}")

print("\n=== '構造' を含む全要素 ===")
for tag in soup.find_all(string=lambda s: s and "構造" in s):
    parent = tag.parent
    print(f"  tag={parent.name!r} class={parent.get('class')} text={tag.strip()!r}")

print("\n=== RC/SRC/木造/鉄骨 を含む全要素 ===")
for kw in ["RC", "SRC", "木造", "鉄骨", "ALC"]:
    for tag in soup.find_all(string=lambda s, kw=kw: s and kw in s):
        parent = tag.parent
        print(f"  [{kw}] tag={parent.name!r} class={parent.get('class')} text={tag.strip()[:60]!r}")
