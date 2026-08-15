"""
建物ページのHTML構造を診断するスクリプト。

使い方:
    docker compose run --rm api python scripts/debug_building.py <building_url>

例:
    docker compose run --rm api python scripts/debug_building.py https://suumo.jp/chintai/bc_100251024420/
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scraper.http import get_soup

url = sys.argv[1] if len(sys.argv) > 1 else input("建物URL: ").strip()

soup = get_soup(url)

print("\n" + "=" * 60)
print("【タイトル系タグ】")
for sel in ["h1", "h2", ".property_view_main-title", ".section_h1-header-title", ".bukken-name"]:
    tags = soup.select(sel)
    for t in tags[:3]:
        print(f"  {sel}: {t.get_text(strip=True)[:80]}")

print("\n" + "=" * 60)
print("【テーブル・DLの全キー/バリュー】")
# th/td パターン
for row in soup.select("tr"):
    th = row.select_one("th")
    td = row.select_one("td")
    if th and td:
        print(f"  th={th.get_text(strip=True)[:30]!r:35s} td={td.get_text(strip=True)[:50]!r}")

# dt/dd パターン
for dl in soup.select("dl"):
    dts = dl.select("dt")
    dds = dl.select("dd")
    for dt, dd in zip(dts, dds):
        print(f"  dt={dt.get_text(strip=True)[:30]!r:35s} dd={dd.get_text(strip=True)[:50]!r}")

print("\n" + "=" * 60)
print("【部屋リンク候補 (href に /jnc_ or /bc_ を含むもの)】")
found = []
for a in soup.find_all("a", href=True):
    href = a["href"]
    if "/jnc_" in href or ("/bc_" in href and href != url):
        if href not in found:
            found.append(href)
            print(f"  {href[:100]}")
if not found:
    print("  (見つからず)")

print("\n" + "=" * 60)
print("【その他リンク (cassetteitem 内)】")
for a in soup.select(".cassetteitem a[href]")[:10]:
    print(f"  {a.get('href', '')[:100]}")
