"""
本格スクレイピング前に、追加候補フィールドが実際にページから取れるか確認する診断スクリプト。

確認対象:
  - 緯度経度（地図埋め込み・script内のlat/lng等）
  - リノベーション/リフォーム済みフラグ
  - 方角（南向き等）
  - 取扱不動産会社名
  - 入居可能日
  - 全th/td（見落としている既存フィールドがないかの確認も兼ねる）

使い方:
    python scripts/debug_new_fields.py <room_url>

例:
    python scripts/debug_new_fields.py https://suumo.jp/chintai/jnc_000012345678/
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scraper.http import get_soup

url = sys.argv[1] if len(sys.argv) > 1 else input("room URL: ").strip()

soup = get_soup(url)
html = str(soup)

print("=" * 60)
print("【全th/td（既存フィールドのマッピング漏れ確認も兼ねる）】")
for row in soup.select("tr"):
    ths = row.find_all("th", recursive=False)
    tds = row.find_all("td", recursive=False)
    for th, td in zip(ths, tds):
        print(f"  th={th.get_text(strip=True)[:20]!r:25s} td={td.get_text(strip=True)[:60]!r}")

print("\n" + "=" * 60)
print("【緯度経度の手がかり】")
lat_patterns = re.findall(r'"?lat"?\s*[:=]\s*"?(-?\d+\.\d+)"?', html, re.IGNORECASE)
lng_patterns = re.findall(r'"?lng"?\s*[:=]\s*"?(-?\d+\.\d+)"?', html, re.IGNORECASE)
lon_patterns = re.findall(r'"?lon(?:gitude)?"?\s*[:=]\s*"?(-?\d+\.\d+)"?', html, re.IGNORECASE)
print(f"  lat候補: {lat_patterns[:5]}")
print(f"  lng候補: {lng_patterns[:5]}")
print(f"  lon候補: {lon_patterns[:5]}")
iframe_maps = [i.get("src", "") for i in soup.select("iframe") if "map" in i.get("src", "").lower()]
print(f"  地図iframe: {iframe_maps[:3]}")

print("\n" + "=" * 60)
print("【方角・向き】")
for kw in ["方角", "向き", "バルコニー向き"]:
    hits = soup.find_all(string=re.compile(kw))
    print(f"  '{kw}' を含むテキスト: {len(hits)}件  例: {[h.strip()[:30] for h in hits[:3]]}")

print("\n" + "=" * 60)
print("【リノベーション/リフォーム】")
for kw in ["リノベ", "リフォーム済", "改装"]:
    hits = soup.find_all(string=re.compile(kw))
    print(f"  '{kw}' を含むテキスト: {len(hits)}件  例: {[h.strip()[:30] for h in hits[:3]]}")

print("\n" + "=" * 60)
print("【取扱不動産会社】")
for sel in [".shop_ttl-txt", ".company_name", ".shopName", ".shop-name"]:
    tags = soup.select(sel)
    for t in tags[:2]:
        print(f"  {sel}: {t.get_text(strip=True)[:40]}")
hits = soup.find_all(string=re.compile("取扱店|株式会社|不動産"))
print(f"  '取扱店/株式会社/不動産' を含むテキスト例: {[h.strip()[:30] for h in hits[:5]]}")

print("\n" + "=" * 60)
print("【入居可能日】")
hits = soup.find_all(string=re.compile("入居可能|入居時期"))
print(f"  該当テキスト: {[h.strip()[:30] for h in hits[:3]]}")
