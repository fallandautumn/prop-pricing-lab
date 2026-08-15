from datetime import datetime
from sqlalchemy import String, Integer, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Building(Base):
    __tablename__ = "buildings"
    __table_args__ = (
        # 名寄せキー: 正規化タイトル + 住所で物理的な建物を一意に識別
        # suumo_building_id (bc_id) は listing 単位で変わるため使えない
        UniqueConstraint("title", "address", name="uq_buildings_title_address"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    suumo_building_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="最初に取得した bc_id（参考情報）"
    )
    title: Mapped[str | None] = mapped_column(String(256))
    address: Mapped[str | None] = mapped_column(String(256))
    age: Mapped[int | None] = mapped_column(Integer, comment="築年数（年）")
    total_floors: Mapped[int | None] = mapped_column(Integer, comment="建物総階数")
    station_distance: Mapped[int | None] = mapped_column(Integer, comment="駅徒歩分")
    building_type: Mapped[str | None] = mapped_column(String(32), comment="マンション・アパート・一軒家")
    building_structure: Mapped[str | None] = mapped_column(
        String(32), comment="RC・SRC・木造・鉄骨など。詳細ページから取得。NULL許容"
    )
    scraped_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    rooms: Mapped[list["Room"]] = relationship("Room", back_populates="building", cascade="all, delete-orphan")
