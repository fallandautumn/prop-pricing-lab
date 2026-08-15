import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests
from dotenv import load_dotenv

load_dotenv()

from app.db.session import SessionLocal
from app.db.models.building import Building
from app.db.models.room import Room
from app.scraper.listing import fetch_building_urls
from app.scraper.building import extract_building_fields, merge_building_data
from app.scraper.room import extract_room_fields, _extract_room_id
from app.scraper.http import get_soup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

# Phase 0/1 は集合住宅（マンション・アパート）が対象。
# 一戸建ては別テンプレートで「賃料」フィールドが標準の詳細テーブルに
# 存在せず（2026-08確認）、価格が常にNULLになってしまうためスキップする。
# 建物タイプ拡張はプロジェクト方針通りestie応募後に対応する。
SKIP_BUILDING_TYPES = {"一戸建て"}


def upsert_building(db, data) -> Building:
    """
    名寄せ: (title, address) で物理的な建物を特定し upsert する。
    同じ建物の別部屋が同一 building row に紐付くようにするための核心ロジック。

    - title + address が両方 non-null → それをキーに lookup
    - どちらかが null → suumo_building_id にフォールバック（精度は落ちるが保存はする）
    """
    building = None

    if data.title and data.address:
        building = (
            db.query(Building)
            .filter_by(title=data.title, address=data.address)
            .first()
        )

    if building is None and data.suumo_building_id:
        # title/address が取れなかった場合のフォールバック
        building = (
            db.query(Building)
            .filter_by(suumo_building_id=data.suumo_building_id)
            .first()
        )

    if building is None:
        building = Building(suumo_building_id=data.suumo_building_id)
        db.add(building)
    elif building.suumo_building_id is None:
        # 既存 row に bc_id が未設定なら補完（最初の bc_id を参考保存）
        building.suumo_building_id = data.suumo_building_id

    building.title = data.title
    building.address = data.address
    building.age = data.age
    building.total_floors = data.total_floors
    building.station_distance = data.station_distance
    building.building_type = data.building_type
    building.building_structure = data.building_structure
    return building


def upsert_room(db, building: Building, data) -> Room:
    room = db.query(Room).filter_by(suumo_room_id=data.suumo_room_id).first()
    if room is None:
        room = Room(suumo_room_id=data.suumo_room_id, building=building)
        db.add(room)
    room.price = data.price
    room.admin_fee = data.admin_fee
    room.monthly_fee = data.monthly_fee
    room.deposit = data.deposit
    room.key_money = data.key_money
    room.liv_area = data.liv_area
    room.floor = data.floor
    room.floor_plan = data.floor_plan
    return room


def main(max_pages: int | None, max_buildings: int | None, start_page: int = 1) -> None:
    logger.info("=== scraping start (page %d〜%s) ===", start_page, max_pages or "終端")

    # Stage 1: {bc_id: [jnc_urls]}
    buildings_map = fetch_building_urls(max_pages=max_pages, max_urls=max_buildings, start_page=start_page)
    total_rooms = sum(len(v) for v in buildings_map.values())
    logger.info("target: %d bc_ids / %d rooms (after 名寄せ: fewer building rows)", len(buildings_map), total_rooms)

    session = requests.Session()
    db = SessionLocal()
    total_bc = len(buildings_map)

    try:
        for i, (bc_id, jnc_urls) in enumerate(buildings_map.items(), 1):
            logger.info("[%d/%d] bc_%s (%d rooms)", i, total_bc, bc_id, len(jnc_urls))

            # 各URLを1回だけフェッチし、room情報とbuilding情報を同じsoupから抽出する。
            # building情報はページによって表示項目が異なるため（種別/構造が
            # 一部のlistingにしか出ない等）、グループ内の全ページ分をマージして
            # 取得率を上げる。
            building_field_dicts = []
            room_data_list = []
            for rurl in jnc_urls:
                try:
                    soup = get_soup(rurl, session)
                except Exception as e:
                    logger.warning("fetch failed, skip: %s (%s)", rurl, e)
                    continue

                building_field_dicts.append(extract_building_fields(soup))

                room_id = _extract_room_id(rurl)
                if room_id is None:
                    logger.warning("room id extraction failed: %s", rurl)
                    continue
                room_data_list.append(extract_room_fields(soup, room_id))

            if not building_field_dicts:
                logger.warning("no pages fetched, skip: bc_%s", bc_id)
                continue

            b_data = merge_building_data(bc_id, building_field_dicts)

            if b_data.building_type in SKIP_BUILDING_TYPES:
                logger.info(
                    "  -> skip (building_type=%s 対象外): %s",
                    b_data.building_type, b_data.title or bc_id,
                )
                continue

            building = upsert_building(db, b_data)
            db.flush()  # get building.id before room inserts

            room_count = 0
            for r_data in room_data_list:
                upsert_room(db, building, r_data)
                room_count += 1

            db.commit()
            logger.info(
                "  -> saved %d rooms (building: %s, type=%s, structure=%s)",
                room_count, building.title or bc_id,
                building.building_type, building.building_structure,
            )

    except KeyboardInterrupt:
        logger.info("interrupted. committed data is preserved.")
        db.rollback()
    except Exception as e:
        logger.exception("unexpected error: %s", e)
        db.rollback()
        raise
    finally:
        db.close()
        session.close()

    logger.info("=== scraping complete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Suumo scraper (Shibuya ward)")
    parser.add_argument("--max-pages", type=int, default=None, help="最後に見るページ番号（絶対値）")
    parser.add_argument("--start-page", type=int, default=1, help="開始ページ番号（続きから取得する場合に指定）")
    parser.add_argument("--max-buildings", type=int, default=None)
    args = parser.parse_args()
    main(max_pages=args.max_pages, max_buildings=args.max_buildings, start_page=args.start_page)
