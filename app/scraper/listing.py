"""
Stage 1: listing page -> {bc_id: [jnc_urls]}

Suumo URL structure (verified):
- Each link on listing page is a room URL (jnc_) with ?bc=XXXXX as building ID
- One card (.cassetteitem) contains multiple jnc_ links with different bc_ids
- Group by bc_id to get per-building room lists

Target area: Shibuya / Shinjuku wards, Tokyo（プロジェクト方針により当面この2区に限定）
"""
import logging
import re

import requests

from app.scraper.http import get_soup

logger = logging.getLogger(__name__)

BASE_URL = "https://suumo.jp"

# 対象エリア（プロジェクト方針: 渋谷区・新宿区に限定。地域拡張はestie応募後）。
# Suumoの区コードは "sc_" + 区名ローマ字。
WARD_CODES = {
    "shibuya": "sc_shibuya",
    "shinjuku": "sc_shinjuku",
}


def fetch_building_urls(
    max_pages: int | None = None,
    max_urls: int | None = None,
    start_page: int = 1,
    ward: str = "shibuya",
) -> dict[str, list[str]]:
    """
    Scan a ward's listing pages and return {bc_id: [jnc_url, ...]} dict.

    Args:
        max_pages:  最後に見るページ番号（start_pageからの相対回数ではなく絶対ページ番号）。
                    例: start_page=6, max_pages=30 -> 6〜30ページを取得。
        max_urls:   Max unique buildings (bc_ids) to collect. Stops immediately on reaching limit.
        start_page: 開始ページ番号（1始まり）。既に取得済みのページを再取得せず
                    続きから取りたい場合に使う。
        ward:       対象区。WARD_CODES のキー（"shibuya" / "shinjuku"）。

    Returns:
        {bc_id: [jnc_url, ...]} dict
    """
    if ward not in WARD_CODES:
        raise ValueError(f"unknown ward: {ward!r}. choices: {list(WARD_CODES)}")
    listing_url = f"{BASE_URL}/chintai/tokyo/{WARD_CODES[ward]}/"

    session = requests.Session()
    result: dict[str, list[str]] = {}
    page = start_page

    while True:
        url = f"{listing_url}?page={page}"
        logger.info("listing page: %s", url)

        try:
            soup = get_soup(url, session)
        except Exception as e:
            logger.error("listing fetch failed page=%d: %s", page, e)
            break

        cards = soup.select(".cassetteitem")
        if not cards:
            logger.info("no cards found, stopping (page=%d)", page)
            break

        done = False
        for card in cards:
            for a in card.select("a[href*='/jnc_']"):
                href = a.get("href", "")
                m_jnc = re.search(r"(/chintai/jnc_\w+/)", href)
                m_bc = re.search(r"[?&]bc=(\w+)", href)
                if not (m_jnc and m_bc):
                    continue
                jnc_url = BASE_URL + m_jnc.group(1)
                bc_id = m_bc.group(1)
                if bc_id not in result:
                    result[bc_id] = []
                if jnc_url not in result[bc_id]:
                    result[bc_id].append(jnc_url)

            # Check limit after each card (one card = one new bc_id at most)
            if max_urls and len(result) >= max_urls:
                logger.info("reached max_urls=%d, stopping", max_urls)
                done = True
                break

        logger.info("page=%d: %d cards, total buildings=%d", page, len(cards), len(result))

        if done:
            break

        if max_pages and page >= max_pages:
            logger.info("reached max_pages=%d, stopping", max_pages)
            break

        next_btn = None
        for a in soup.select(".pagination-parts a[href]"):
            if "次へ" in a.get_text():
                next_btn = a
                break
        if next_btn is None:
            break

        page += 1

    total_rooms = sum(len(v) for v in result.values())
    logger.info("done: %d buildings / %d rooms", len(result), total_rooms)
    return result
