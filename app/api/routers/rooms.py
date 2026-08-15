"""
/rooms エンドポイント

主用途: divergence_rate（裁定スコア）でソートして割安物件を発見する。
divergence_rate < 0 が「市場価格 < 適正価格」= 割安。
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session, joinedload

from app.api.schemas.room import RoomOut, RoomsResponse
from app.db.models.building import Building
from app.db.models.room import Room
from app.db.session import get_db

router = APIRouter(prefix="/rooms", tags=["rooms"])

SORTABLE_FIELDS = {
    "divergence_rate": Room.divergence_rate,
    "price": Room.price,
    "estimated_price": Room.estimated_price,
    "liv_area": Room.liv_area,
    "age": Building.age,
    "station_distance": Building.station_distance,
}


@router.get("", response_model=RoomsResponse)
def list_rooms(
    db: Session = Depends(get_db),
    sort: Literal[
        "divergence_rate", "price", "estimated_price", "liv_area", "age", "station_distance"
    ] = Query("divergence_rate", description="ソートキー"),
    order: Literal["asc", "desc"] = Query(
        "asc", description="divergence_rateはascが割安順（デフォルト）"
    ),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    building_type: str | None = Query(None, description="例: マンション"),
    floor_plan: str | None = Query(None, description="例: 1LDK"),
    min_price: int | None = Query(None, ge=0),
    max_price: int | None = Query(None, ge=0),
    max_divergence_rate: float | None = Query(
        None, description="この値以下の乖離率のみ返す（例: -0.1 で10%以上割安のみ）"
    ),
    scored_only: bool = Query(
        True, description="divergence_rate が計算済みの物件のみ返す（デフォルトTrue）"
    ),
):
    """
    賃貸物件一覧を返す。デフォルトでは divergence_rate 昇順（最も割安な物件から）。
    """
    query = db.query(Room).join(Building, Room.building_id == Building.id).options(
        joinedload(Room.building)
    )

    if scored_only:
        query = query.filter(Room.divergence_rate.isnot(None))
    if building_type:
        query = query.filter(Building.building_type == building_type)
    if floor_plan:
        query = query.filter(Room.floor_plan == floor_plan)
    if min_price is not None:
        query = query.filter(Room.price >= min_price)
    if max_price is not None:
        query = query.filter(Room.price <= max_price)
    if max_divergence_rate is not None:
        query = query.filter(Room.divergence_rate <= max_divergence_rate)

    total = query.count()

    sort_col = SORTABLE_FIELDS[sort]
    order_fn = asc if order == "asc" else desc
    query = query.order_by(order_fn(sort_col))

    rooms = query.offset(offset).limit(limit).all()

    items = [
        RoomOut(
            room_id=r.id,
            suumo_room_id=r.suumo_room_id,
            building_id=r.building_id,
            title=r.building.title,
            address=r.building.address,
            age=r.building.age,
            total_floors=r.building.total_floors,
            station_distance=r.building.station_distance,
            building_type=r.building.building_type,
            building_structure=r.building.building_structure,
            price=r.price,
            admin_fee=r.admin_fee,
            monthly_fee=r.monthly_fee,
            deposit=r.deposit,
            key_money=r.key_money,
            liv_area=r.liv_area,
            floor=r.floor,
            floor_plan=r.floor_plan,
            estimated_price=r.estimated_price,
            divergence_rate=r.divergence_rate,
        )
        for r in rooms
    ]

    return RoomsResponse(total=total, limit=limit, offset=offset, items=items)


@router.get("/{room_id}", response_model=RoomOut)
def get_room(room_id: int, db: Session = Depends(get_db)):
    """単一物件の詳細を返す。"""
    room = (
        db.query(Room)
        .options(joinedload(Room.building))
        .filter(Room.id == room_id)
        .first()
    )
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")

    return RoomOut(
        room_id=room.id,
        suumo_room_id=room.suumo_room_id,
        building_id=room.building_id,
        title=room.building.title,
        address=room.building.address,
        age=room.building.age,
        total_floors=room.building.total_floors,
        station_distance=room.building.station_distance,
        building_type=room.building.building_type,
        building_structure=room.building.building_structure,
        price=room.price,
        admin_fee=room.admin_fee,
        monthly_fee=room.monthly_fee,
        deposit=room.deposit,
        key_money=room.key_money,
        liv_area=room.liv_area,
        floor=room.floor,
        floor_plan=room.floor_plan,
        estimated_price=room.estimated_price,
        divergence_rate=room.divergence_rate,
    )
