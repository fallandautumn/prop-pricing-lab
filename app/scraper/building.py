"""
Stage 2: Extract building-level info from a jnc_ (room detail) page.

Key insight: Suumo jnc_ page h1 often includes room number (e.g. "Urban Breeze Ebisu 403goshitsu").
bc_id is per-listing, not per-building.
-> Normalize title (strip room number) + use (title, address) as building identity.
"""
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date

import requests

from app.scraper.http import get_soup

logger = logging.getLogger(__name__)


@dataclass
class BuildingData:
    suumo_building_id: str          # bc_{id} of first encountered listing
    title: str | None = None        # normalized (room number stripped)
    address: str | None = None
    age: int | None = None
    total_floors: int | None = None
    station_distance: int | None = None
    building_type: str | None = None
    building_structure: str | None = None
    total_units: int | None = None


def extract_building_fields(soup) -> dict:
    """
    soup から building レベルのフィールドを辞書で抽出する（HTTPアクセスなし）。

    同じ建物でも listing（room）ページによって表示される項目が異なる
    （例: あるページには「種別」「構造」が無いが別ページにはある）。
    このため単一ページからの抽出結果を複数ページ分マージする設計にしている。
    値が取れなかったフィールドはキー自体を含めない（マージ時に None で上書きしないため）。
    """
    fields: dict = {}

    h1 = soup.select_one("h1")
    if h1:
        title = _normalize_title(h1.get_text(strip=True))
        if title:
            fields["title"] = title

    for th, td in _iter_detail_pairs(soup):
        key = th.get_text(strip=True)
        val = td.get_text(strip=True)

        if "所在地" in key or "住所" in key:
            v = _normalize_text(val)
            if v:
                fields["address"] = v
        elif "築" in key and "年" in key:
            v = _parse_age(val)
            if v is not None:
                fields["age"] = v
        elif "駅" in key and "徒歩" in key:
            v = _parse_station_distance(val)
            if v is not None:
                fields["station_distance"] = v
        elif "階建" in key:
            m = re.search(r"(\d+)階建", val)
            if m:
                fields["total_floors"] = int(m.group(1))
        elif "種別" in key:
            v = val[:32] if val and val != "-" else None
            if v:
                fields["building_type"] = v
        elif "構造" in key:
            v = _normalize_structure(val)
            if v:
                fields["building_structure"] = v
        elif "総戸数" in key:
            m = re.search(r"(\d+)", val)
            if m:
                fields["total_units"] = int(m.group(1))

    return fields


def merge_building_data(bc_id: str, field_dicts: list[dict]) -> BuildingData:
    """
    同一建物の複数ページ分の extract_building_fields() 結果をマージする。
    各フィールドは「リスト内で最初に見つかった非NULL値」を採用する。
    """
    merged: dict = {}
    for fields in field_dicts:
        for k, v in fields.items():
            if k not in merged:
                merged[k] = v
    return BuildingData(suumo_building_id=f"bc_{bc_id}", **merged)


def scrape_building(
    bc_id: str,
    first_jnc_url: str,
    session: requests.Session | None = None,
) -> BuildingData | None:
    """
    単一URLからbuilding情報を取得する（デバッグ・単体テスト用）。
    本番のスクレイピングでは run_scraper.py が複数ページを
    extract_building_fields() + merge_building_data() でマージする方式を使う。
    """
    try:
        soup = get_soup(first_jnc_url, session)
    except Exception as e:
        logger.error("building scrape failed (bc_id=%s, url=%s): %s", bc_id, first_jnc_url, e)
        return None

    fields = extract_building_fields(soup)
    data = BuildingData(suumo_building_id=f"bc_{bc_id}", **fields)
    logger.info("building scraped: %s (bc_%s)", data.title or bc_id, bc_id)
    return data


# ---------- helpers ----------

def _iter_detail_pairs(soup):
    """
    詳細テーブルの th/td を「行内の位置順」でペアリングして返す。

    <tr> 直下の th/td をクラス名を問わず全て拾い、位置順にzipする。
    room.py と同じ対策（1 <tr> に th/td ペアが複数入り、かつ
    property_view_table-title/-body や data_01/data_02 等
    複数のクラス体系が混在するため、特定クラスへの限定はしない）。
    building_structure(構造) は th.data_02 / class無しtd という
    別クラス体系で提供されており、これが欠落の原因だった。
    """
    for row in soup.select("tr"):
        ths = row.find_all("th", recursive=False)
        tds = row.find_all("td", recursive=False)
        for th, td in zip(ths, tds):
            yield th, td


def _normalize_title(title: str) -> str:
    """
    建物タイトルを正規化する。

    1. NFKC 正規化: 全角英数字・スペースを半角に統一
       e.g. "ＳＡＳＡＺＵＫＡ　ＴＯＤＡＹ" -> "SASAZUKA TODAY"
    2. 号室サフィックスを除去
       e.g. "Urban Breeze Ebisu 403号室" -> "Urban Breeze Ebisu"
    3. 連続スペースを単一スペースに圧縮
    4. 末尾のローマ数字を算用数字に正規化
       e.g. "レジディア代々木II" -> "レジディア代々木2"
       （"レジディア代々木2" と表記ゆれで同一視できるようにするため。
       listingによってどちらの表記が使われるか揺れることが分かっている。）
    """
    title = _normalize_text(title)                          # NFKC + スペース圧縮
    title = re.sub(r'\s*\d+[A-Za-z]*号室?\s*$', '', title)  # 末尾の号室を除去（"3F号室"等の表記ゆれ含む）
    title = re.sub(r'\s+[A-Z]?\d{3,4}\s*$', '', title)     # 末尾の英数字部屋番号を除去
    title = normalize_roman_suffix(title.strip())
    return title.strip()


GENERIC_TITLE_PATTERN = re.compile(r"駅.*階建.*築|築.*駅.*階建")


def is_generic_title(title: str | None) -> bool:
    """
    Suumoの一部ページ（主に新築・正式名称が未確定の物件）は、h1が実際の
    建物名ではなく「路線 駅名 階建 築年数」という自動生成の要約文になる。
    この要約文は表示される最寄り駅がlistingごとに揺れるため
    （例: 同じ建物なのに「初台駅」表記と「幡ヶ谷駅」表記が混在する）、
    (title, address) の名寄せキーとして信頼できない。
    """
    if not title:
        return False
    return bool(GENERIC_TITLE_PATTERN.search(title))


_ROMAN_SUFFIX_MAP = [
    ("VIII", "8"),
    ("VII", "7"),
    ("III", "3"),
    ("IV", "4"),
    ("IX", "9"),
    ("VI", "6"),
    ("II", "2"),
    ("V", "5"),
    ("I", "1"),
]


def normalize_roman_suffix(title: str) -> str:
    """
    建物名の末尾が半角ローマ数字（NFKC正規化により全角ローマ数字は
    事前にASCIIへ分解済み）の場合、算用数字に変換する。
    e.g. "レジディア代々木II" / "レジディア代々木Ⅱ"(NFKC後II) -> "レジディア代々木2"

    既知のリスク: 建物名が偶然 "...I" "...V" 等で終わる場合に誤変換する
    可能性はあるが、日本の賃貸物件名では意図的なローマ数字の棟番号
    （フォレストI、テラスII等）である場合が大半のため許容している。
    """
    for roman, arabic in _ROMAN_SUFFIX_MAP:
        if title.endswith(roman):
            base = title[: -len(roman)].rstrip()
            return base + arabic
    return title


def _normalize_text(text: str) -> str:
    """NFKC + 連続スペース圧縮。title と address 両方に適用する。"""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def _parse_age(text: str) -> int | None:
    """
    バグ修正メモ（2026-08）:
    Suumoの築年数フィールドは2つの表記が混在する:
      a) '築7年' のように既に築年数（経過年数）の形式
      b) '2019年3月' のように建築年月（西暦）そのものの形式
    旧実装は `(\\d+)\\s*年` で最初にマッチした数字をそのまま年数として
    扱っていたため、(b) の場合に西暦（2019等）がそのままageに入っていた。
    西暦4桁（19xx/20xx）を先に判定し、該当すれば
    `現在年 - 建築年` で経過年数に変換する。
    """
    if not text or text == "-":
        return None
    if "新築" in text:
        return 0

    # (b) 建築年（西暦4桁）表記: '2019年3月' 等
    m_year = re.search(r"(19|20)\d{2}(?=年)", text)
    if m_year:
        build_year = int(m_year.group(0))
        return max(date.today().year - build_year, 0)

    # (a) 既に築年数（経過年数）の表記: '築7年' 等
    m_age = re.search(r"(\d+)\s*年", text)
    return int(m_age.group(1)) if m_age else None


def _parse_station_distance(text: str) -> int | None:
    m = re.search(r"歩(\d+)分", text)
    return int(m.group(1)) if m else None


def _normalize_structure(text: str) -> str | None:
    """
    Suumoの構造表記は省略形が多い（例: '鉄筋コン' = 鉄筋コンクリート）。
    より具体的な表記を先にチェックする順序が重要
    （'鉄骨鉄筋コン' は '鉄筋コン' も含むため先に判定しないとRC誤判定になる）。
    """
    if not text or text == "-":
        return None

    upper = text.upper()
    for code in ("SRC", "RC", "ALC"):
        if code in upper:
            return code

    mapping = [
        ("鉄骨鉄筋コン", "SRC"),   # 鉄骨鉄筋コンクリート
        ("鉄筋コン", "RC"),       # 鉄筋コンクリート
        ("軽量鉄骨", "軽量鉄骨"),
        ("重量鉄骨", "重量鉄骨"),
        ("鉄骨", "鉄骨"),
        ("木造", "木造"),
    ]
    for label, code in mapping:
        if label in text:
            return code

    return text[:32]
