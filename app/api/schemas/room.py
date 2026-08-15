"""API レスポンススキーマ（rooms + buildings を結合したフラットな形）"""
from pydantic import BaseModel


class RoomOut(BaseModel):
    room_id: int
    suumo_room_id: str

    # 建物情報
    building_id: int
    title: str | None = None
    address: str | None = None
    age: int | None = None
    total_floors: int | None = None
    station_distance: int | None = None
    building_type: str | None = None
    building_structure: str | None = None

    # 部屋情報
    price: int | None = None
    admin_fee: int | None = None
    monthly_fee: int | None = None
    deposit: int | None = None
    key_money: int | None = None
    liv_area: float | None = None
    floor: int | None = None
    floor_plan: str | None = None

    # モデル出力
    estimated_price: int | None = None
    divergence_rate: float | None = None


class RoomsResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[RoomOut]
