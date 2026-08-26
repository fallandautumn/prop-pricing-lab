"""add orientation/move_in_date/url to rooms, total_units to buildings

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-08-25 00:00:00.000000

本格スクレイピング（渋谷区フル再取得）前に、debug_new_fields.pyでの
ページ調査で実在を確認したフィールドを追加する。
- rooms.orientation: 向き（例: 南、西）。既知の価格要因。
- rooms.move_in_date: 入居可能時期（生テキスト）。交渉余地の代理変数になりうる。
- rooms.url: Suumo物件詳細URL。デバッグ用（従来はsuumo_room_idから逆算していた）。
- buildings.total_units: 総戸数。建物規模の情報。

緯度経度・リノベーションフラグ・不動産会社名は該当ページで確実に
取得できなかったため見送り（将来、地価データ統合フェーズで別途調査）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('rooms', sa.Column('orientation', sa.String(length=8), nullable=True,
                   comment='向き（例: 南、西）'))
    op.add_column('rooms', sa.Column('move_in_date', sa.String(length=32), nullable=True,
                   comment="入居可能時期（生テキスト。例: '26年10月下旬）"))
    op.add_column('rooms', sa.Column('url', sa.String(length=255), nullable=True,
                   comment='Suumo物件詳細URL（デバッグ用）'))
    op.add_column('buildings', sa.Column('total_units', sa.Integer(), nullable=True,
                   comment='総戸数'))


def downgrade() -> None:
    op.drop_column('buildings', 'total_units')
    op.drop_column('rooms', 'url')
    op.drop_column('rooms', 'move_in_date')
    op.drop_column('rooms', 'orientation')
