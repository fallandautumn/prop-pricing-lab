"""building dedup by title address

Revision ID: b3c2d1e4f5a6
Revises: afacbca20615
Create Date: 2026-07-01 00:00:00.000000

suumo_building_id は掲載単位で変わるため建物の一意識別に使えない。
(title, address) を名寄せキーとして UniqueConstraint に変更する。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3c2d1e4f5a6'
down_revision: Union[str, None] = 'afacbca20615'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. suumo_building_id の unique 制約を削除・nullable に変更
    op.drop_constraint('buildings_suumo_building_id_key', 'buildings', type_='unique')
    op.alter_column('buildings', 'suumo_building_id',
                    existing_type=sa.String(length=64),
                    nullable=True,
                    comment='最初に取得した bc_id（参考情報）')

    # 2. (title, address) に複合 unique 制約を追加（名寄せキー）
    op.create_unique_constraint('uq_buildings_title_address', 'buildings', ['title', 'address'])


def downgrade() -> None:
    op.drop_constraint('uq_buildings_title_address', 'buildings', type_='unique')
    op.alter_column('buildings', 'suumo_building_id',
                    existing_type=sa.String(length=64),
                    nullable=False)
    op.create_unique_constraint('buildings_suumo_building_id_key', 'buildings', ['suumo_building_id'])
