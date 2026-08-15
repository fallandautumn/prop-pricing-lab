"""賃料フィールドが取れない原因を調査する。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.scraper.http import get_soup
from app.scraper.room import _iter_detail_pairs

url = sys.argv[1] if len(sys.argv) > 1 else input("部屋URL: ").strip()
soup = get_soup(url)

print("=== _iter_detail_pairs で拾えるペア ===")
for th, td in _iter_detail_pairs(soup):
    key = th.get_text(strip=True)
    val = td.get_text(strip=True)
    marker = " <== 賃料っぽい" if "賃料" in key else ""
    print(f"  {key!r}: {val!r}{marker}")

print("\n=== '賃料' を含む全要素（タグ種別問わず）===")
for tag in soup.find_all(string=lambda s: s and "賃料" in s):
    parent = tag.parent
    print(f"  tag={parent.name!r} class={parent.get('class')} text={tag.strip()!r}")
