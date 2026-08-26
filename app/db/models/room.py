from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    building_id: Mapped[int] = mapped_column(Integer, ForeignKey("buildings.id"), nullable=False)
    suumo_room_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    # 賃料関連（すべて円）
    price: Mapped[int | None] = mapped_column(Integer, comment="賃料（円）")
    admin_fee: Mapped[int | None] = mapped_column(Integer, comment="管理費（円）")
    monthly_fee: Mapped[int | None] = mapped_column(Integer, comment="price + admin_fee（円）")
    deposit: Mapped[int | None] = mapped_column(Integer, comment="敷金（円）")
    key_money: Mapped[int | None] = mapped_column(Integer, comment="礼金（円）")

    # 部屋属性
    liv_area: Mapped[float | None] = mapped_column(Float, comment="専有面積（㎡）")
    floor: Mapped[int | None] = mapped_column(Integer, comment="部屋の階数")
    floor_plan: Mapped[str | None] = mapped_column(String(16), comment="間取り（例: 1LDK）")
    orientation: Mapped[str | None] = mapped_column(String(8), comment="向き（例: 南、西）")
    move_in_date: Mapped[str | None] = mapped_column(String(32), comment="入居可能時期（生テキスト。例: '26年10月下旬）")
    url: Mapped[str | None] = mapped_column(String(255), comment="Suumo物件詳細URL（デバッグ用）")

    # モデル出力（Phase1以降に更新）
    estimated_price: Mapped[int | None] = mapped_column(Integer, comment="適正価格（円）。モデル実行後に保存")
    divergence_rate: Mapped[float | None] = mapped_column(Float, comment="裁定スコア = (market - estimated) / estimated")

    # Phase2
    brand_score: Mapped[float | None] = mapped_column(Float, comment="LLMブランドスコア（Phase2）")

    scraped_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    building: Mapped["Building"] = relationship("Building", back_populates="rooms")
