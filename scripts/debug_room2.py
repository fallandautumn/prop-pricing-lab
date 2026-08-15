"""面積フィールドの実際のDOM構造を特定する。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.scraper.http import get_soup

url = sys.argv[1] if len(sys.argv) > 1 else input("部屋URL: ").strip()
soup = get_soup(url)

# 1. "面積"を含む全要素を探す（タグ種別問わず）
print("=" * 60)
print("【'面積' を含む全要素】")
print("=" * 60)
for tag in soup.find_all(string=lambda s: s and "面積" in s):
    parent = tag.parent
    print(f"  tag={parent.name!r} class={parent.get('class')} text={tag.strip()!r}")

# 2. "m2" or "㎡" を含む全要素
print("\n" + "=" * 60)
print("【'㎡' を含む全要素】")
print("=" * 60)
for tag in soup.find_all(string=lambda s: s and "㎡" in s):
    parent = tag.parent
    print(f"  tag={parent.name!r} class={parent.get('class')} text={tag.strip()!r}")
