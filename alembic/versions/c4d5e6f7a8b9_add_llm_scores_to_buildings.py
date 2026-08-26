"""add llm brand/location scores to buildings

Revision ID: c4d5e6f7a8b9
Revises: b3c2d1e4f5a6
Create Date: 2026-08-20 00:00:00.000000

Phase2: OpenAI API (gpt-4o-mini) で物件名・住所からブランドスコア・
立地スコアを生成する。部屋番号に依存しない建物単位の属性のため
buildings テーブルに追加する（rooms.brand_score は初期スタブのまま残置）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3c2d1e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('buildings', sa.Column('brand_score', sa.Float(), nullable=True,
                   comment='LLMブランドスコア(0-100)。デベロッパーブランド・シリーズの評価'))
    op.add_column('buildings', sa.Column('location_score', sa.Float(), nullable=True,
                   comment='LLM立地スコア(0-100)。駅距離を除いたエリアの格・利便性の評価'))
    op.add_column('buildings', sa.Column('llm_reasoning', sa.Text(), nullable=True,
                   comment='LLMスコアの根拠（デバッグ・説明可能性のため保存）'))
    op.add_column('buildings', sa.Column('llm_scored_at', sa.DateTime(), nullable=True,
                   comment='LLMスコアリングを実行した日時。再実行時のスキップ判定に使う'))


def downgrade() -> None:
    op.drop_column('buildings', 'llm_scored_at')
    op.drop_column('buildings', 'llm_reasoning')
    op.drop_column('buildings', 'location_score')
    op.drop_column('buildings', 'brand_score')
