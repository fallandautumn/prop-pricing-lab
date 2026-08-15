"""
一覧ページと建物ページ（bc_）のHTML構造を診断するスクリプト。

【手順】
1. 一覧ページを診断（引数なし or --listing）
   docker compose run --rm api python scripts/debug_listing.py

2. 取得された bc_ URL を建物ページとして診断（--bc <url>）
   docker compose run --rm api python scripts/debug_listing.py --bc https://suumo.jp/chintai/bc_XXXXXXXXXX/
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scraper.http import get_soup

LISTING_URL = "https://suumo.jp/chintai/tokyo/sc_shibuya/?page=1"

parser = argparse.ArgumentParser()
parser.add_argument("--bc", help="建物ページURL（bc_）を直接指定して診断")
args = parser.parse_args()

# ==================== 一覧ページ診断 ====================
if not args.bc:
    print(f"\n{'='*60}")
    print(f"【一覧ページ診断】{LISTING_URL}")
    soup = get_soup(LISTING_URL)

    cards = soup.select(".cassetteitem")
    print(f"\n.cassetteitem カード数: {len(cards)}")

    if cards:
        print("\n--- 1枚目のカードの全リンク ---")
        card = cards[0]
        for a in card.find_all("a", href=True):
            text = a.get_text(strip=True)[:20]
            href = a["href"]
            print(f"  text={text!r:25s} href={href[:80]}")

        print("\n--- .js-cassette_link_href の href ---")
        for a in card.select(".js-cassette_link_href"):
            print(f"  {a.get('href','')}")

        print("\n--- bc_ / jnc_ を含むリンク（全カード） ---")
        bc_urls, jnc_urls = set(), set()
        for c in cards:
            for a in c.find_all("a", href=True):
                h = a["href"]
                if "/bc_" in h:
                    bc_urls.add(h)
                elif "/jnc_" in h:
                    jnc_urls.add(h)
        print(f"  bc_ リンク数: {len(bc_urls)}")
        for u in list(bc_urls)[:5]:
            print(f"    {u}")
        print(f"  jnc_ リンク数: {len(jnc_urls)}")
        for u in list(jnc_urls)[:5]:
            print(f"    {u}")

        print("\n--- ページネーション ---")
        for a in soup.select(".pagination-parts a"):
            print(f"  text={a.get_text(strip=True)!r} href={a.get('href','')[:60]}")

    else:
        print("\n⚠️  .cassetteitem が見つかりません")
        print("\n--- ページ内の主要クラス（参考） ---")
        for tag in soup.find_all(class_=True)[:30]:
            classes = " ".join(tag.get("class", []))
            print(f"  <{tag.name}> class={classes[:60]}")

# ==================== 建物ページ（bc_）診断 ====================
else:
    url = args.bc
    print(f"\n{'='*60}")
    print(f"【建物ページ診断】{url}")
    soup = get_soup(url)

    print("\n--- タイトル ---")
    for sel in ["h1", ".section_h1-header-title", ".property_view_main-title"]:
        for t in soup.select(sel)[:2]:
            print(f"  {sel}: {t.get_text(strip=True)[:80]}")

    print("\n--- 全 th/td ---")
    for row in soup.select("tr"):
        th = row.select_one("th")
        td = row.select_one("td")
        if th and td:
            print(f"  {th.get_text(strip=True)[:30]!r:35s} => {td.get_text(strip=True)[:60]!r}")

    print("\n--- 全 dt/dd ---")
    for dl in soup.select("dl"):
        for dt, dd in zip(dl.select("dt"), dl.select("dd")):
            k = dt.get_text(strip=True)
            v = dd.get_text(strip=True)
            if k and v and k not in ("借りる", "マンションを買う", "一戸建てを買う", "建てる", "リフォームする", "売る", "住まいの相談"):
                print(f"  {k[:30]!r:35s} => {v[:60]!r}")

    print("\n--- jnc_ リンク（部屋URL候補） ---")
    jnc = []
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if "/jnc_" in h and h not in jnc:
            jnc.append(h)
    print(f"  jnc_ リンク数: {len(jnc)}")
    for u in jnc[:10]:
        print(f"  {u}")

    print("\n--- cassetteitem 内のリンク ---")
    for a in soup.select(".cassetteitem a[href]")[:10]:
        print(f"  {a.get('href','')[:80]}")
