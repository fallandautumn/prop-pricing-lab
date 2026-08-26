from datetime import datetime
from sqlalchemy import String, Integer, Float, Text, DateTime, UniqueConstraint, func
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
    total_units: Mapped[int | None] = mapped_column(Integer, comment="総戸数")
    # Phase2: LLM（gpt-4o-mini）による物件名・住所からのスコアリング
    # brand/locationは部屋番号に依存しない建物単位の属性のため buildings に持たせる
    # （rooms.brand_score は初期スタブとして残っているが未使用・非推奨）
    brand_score: Mapped[float | None] = mapped_column(
        Float, comment="LLMブランドスコア(0-100)。デベロッパーブランド・シリーズの評価"
    )
    location_score: Mapped[float | None] = mapped_column(
        Float, comment="LLM立地スコア(0-100)。駅距離を除いたエリアの格・利便性の評価"
    )
    llm_reasoning: Mapped[str | None] = mapped_column(
        Text, comment="LLMスコアの根拠（デバッグ・説明可能性のため保存）"
    )
    llm_scored_at: Mapped[datetime | None] = mapped_column(
        DateTime, comment="LLMスコアリングを実行した日時。再実行時のスキップ判定に使う"
    )

    scraped_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    rooms: Mapped[list["Room"]] = relationship("Room", back_populates="building", cascade="all, delete-orphan")
