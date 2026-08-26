"""
Stage 3: Room detail page (jnc_) -> room info

Verified th key names on Suumo jnc_ pages:
- 'chintai(kanrihi)' -> '15.8manen(12000en)' (price + admin fee in one field)
- 'kaitachi'         -> '3kai/6kaitachi'      (room floor / building total floors)
- 'madori'          -> '1DK'
- 'shikikin'/'reikin' -> '1kagetsu' or '15.8manen' or '-'
- 'senyumenseki'    -> '28.5m2'

構造バグ修正メモ（2026-08）:
- 詳細テーブルの1 <tr> に th/td ペアが2組入っている行がある
  (例: <th>間取り</th><td>1LDK</td><th>専有面積</th><td>41.38m<sup>2</sup></td>)
  row.select_one("th")/select_one("td") は最初のペアしか取れず、
  2番目のペア（liv_area等）が構造的に必ず欠落していた。
- さらにSuumoの詳細テーブルは複数のクラス体系が混在する:
    a) th.property_view_table-title / td.property_view_table-body（賃料・面積等）
    b) th.data_01/data_02（class無しtd）（構造・間取り詳細等）
  クラス名を特定のものに限定すると (b) を取りこぼす。
  -> tr直下のth/tdをクラスに関係なく位置順でzipする汎用ロジックに変更。
"""
import logging
import re
from dataclasses import dataclass

import requests

from app.scraper.http import get_soup

logger = logging.getLogger(__name__)


@dataclass
class RoomData:
    suumo_room_id: str
    price: int | None = None
    admin_fee: int | None = None
    monthly_fee: int | None = None
    deposit: int | None = None
    key_money: int | None = None
    liv_area: float | None = None
    floor: int | None = None
    floor_plan: str | None = None
    orientation: str | None = None
    move_in_date: str | None = None
    url: str | None = None


def extract_room_fields(soup, room_id: str) -> RoomData:
    """
    soup から room データを抽出する（HTTPアクセスなし）。
    run_scraper.py 側で building 情報も同じ soup から一緒に抽出するために分離した。
    """
    data = RoomData(suumo_room_id=room_id)

    for th, td in _iter_detail_pairs(soup):
        key = th.get_text(strip=True)
        val = td.get_text(strip=True)

        if "賃料" in key:
            # '賃料' = chintai. Key is '賃料(管理費)' on Suumo.
            # Value like '15.8万円(12000円)' -> price + admin_fee
            _parse_price_and_admin(val, data)
        elif "敷金" in key:   # shikikin
            data.deposit = _parse_yen_or_months(val, data.price)
        elif "礼金" in key:   # reikin
            data.key_money = _parse_yen_or_months(val, data.price)
        elif "専有面積" in key:
            # senyumenseki: 主たる面積。バルコニー等の副フィールドより常に優先。
            data.liv_area = _parse_area(val)
        elif (
            "面積" in key
            and "間取り" not in key
            and data.liv_area is None
            and not any(x in key for x in ("バルコニー", "駐車場", "専用庭", "トランクルーム", "ルーフ"))
        ):
            # フォールバック: '専有面積' 表記が無いページ用。
            # 一度セットされたら上書きしない（バルコニー面積等での事故防止）。
            data.liv_area = _parse_area(val)
        elif "階建" in key:
            # '階建' = kaitachi. '3階/6階建' -> floor=3
            m = re.match(r"(\d+)階", val)
            data.floor = int(m.group(1)) if m else None
        elif "間取り" in key and "詳細" not in key:
            # madori (but not madori-shosai)
            data.floor_plan = val[:16]
        elif key == "向き":
            # 完全一致に限定（"バルコニー向き"等の別フィールドとの誤取得防止）
            data.orientation = val[:8] if val and val != "-" else None
        elif "入居" in key:
            # 表記ゆれ（"入居"/"入居時期"/"入居可能"等）に対応するため部分一致。
            # 生テキストのまま保存（例: "'26年10月下旬"、"即時"等、書式が統一されていないため）
            data.move_in_date = val[:32] if val and val != "-" else None

    if data.price is not None:
        data.monthly_fee = data.price + (data.admin_fee or 0)

    logger.debug("room scraped: %s price=%s admin=%s", room_id, data.price, data.admin_fee)
    return data


def scrape_room(url: str, session: requests.Session | None = None) -> RoomData | None:
    """
    単一URLからroom情報を取得する（デバッグ・単体テスト用）。
    本番のスクレイピングでは run_scraper.py が extract_room_fields() を直接使う
    （building情報と同じ soup から一括抽出するため、二重フェッチを避ける）。
    """
    room_id = _extract_room_id(url)
    if not room_id:
        logger.warning("room id extraction failed: %s", url)
        return None

    try:
        soup = get_soup(url, session)
    except Exception as e:
        logger.error("room page fetch failed %s: %s", url, e)
        return None

    data = extract_room_fields(soup, room_id)
    data.url = url
    return data


# ---------- helpers ----------

def _iter_detail_pairs(soup):
    """
    詳細テーブルの th/td を「行内の位置順」でペアリングして返す。

    <tr> 直下の th/td をクラス名を問わず全て拾い、位置順にzipする。
    Suumoの詳細テーブルは1 <tr> に th/td ペアが1〜2組入り、かつ
    ページ内で複数のクラス体系（property_view_table-title/-body、
    data_01/data_02 等）が混在するため、特定クラスへの限定はしない。
    recursive=False でネストしたテーブルの混入は防ぐ。
    """
    for row in soup.select("tr"):
        ths = row.find_all("th", recursive=False)
        tds = row.find_all("td", recursive=False)
        for th, td in zip(ths, tds):
            yield th, td


def _extract_room_id(url: str) -> str | None:
    m = re.search(r"/jnc_(\w+)/?", url)
    return f"jnc_{m.group(1)}" if m else None


def _parse_price_and_admin(text: str, data: RoomData) -> None:
    """
    '15.8manen(12000en)' -> price=158000, admin_fee=12000
    '15.8manen(1.2manen)' -> price=158000, admin_fee=12000
    '15.8manen' -> price=158000, admin_fee=None
    """
    m_price = re.search(r"([\d.]+)\s*万", text)   # X.X-man
    if m_price:
        data.price = int(float(m_price.group(1)) * 10000)
    # admin fee is inside parentheses
    m_paren = re.search(r"\(([^)]+)\)", text)
    if m_paren:
        data.admin_fee = _parse_yen(m_paren.group(1))


def _parse_yen(text: str) -> int | None:
    text = text.strip()
    if not text or text in ("-", "なし"):  # '-' or 'nashi'
        return None
    m = re.search(r"([\d.]+)\s*万", text)   # X.X-man
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"([\d,]+)\s*円", text)   # X,XXX-en
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def _parse_yen_or_months(text: str, price: int | None) -> int | None:
    """
    Deposit/key money: '1kagetsu' (multiple of rent) or '15.8manen' or '-'
    """
    text = text.strip()
    if not text or text in ("-", "なし"):
        return None
    yen = _parse_yen(text)
    if yen is not None:
        return yen
    # month notation
    m = re.search(r"([\d.]+)\s*[ヶか]月", text)  # X-kagetsu
    if m and price is not None:
        return int(float(m.group(1)) * price)
    return None


def _parse_area(text: str) -> float | None:
    m = re.search(r"([\d.]+)\s*[m㎡]", text)
    return float(m.group(1)) if m else None
