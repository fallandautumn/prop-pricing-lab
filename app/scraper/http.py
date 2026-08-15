"""共通の HTTP クライアント。レート制限（1秒以上のスリープ）を一元管理する。"""
import time
import random
import logging

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9",
}

# リクエスト間の最小・最大スリープ秒数（Suumoへの過負荷を防ぐ）
SLEEP_MIN = 1.5
SLEEP_MAX = 3.0


def get_soup(url: str, session: requests.Session | None = None) -> BeautifulSoup:
    """URL を取得して BeautifulSoup を返す。自動でスリープを入れる。"""
    client = session or requests.Session()
    logger.debug("GET %s", url)
    resp = client.get(url, headers=BASE_HEADERS, timeout=15)
    resp.raise_for_status()
    _sleep()
    return BeautifulSoup(resp.text, "lxml")


def _sleep() -> None:
    duration = random.uniform(SLEEP_MIN, SLEEP_MAX)
    logger.debug("sleep %.2fs", duration)
    time.sleep(duration)
