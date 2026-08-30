"""add quality_score to spider_results

Revision ID: ce5210dedbd4
Revises: 007
Create Date: 2026-08-26 11:02:42.934572

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce5210dedbd4'
down_revision: Union[str, Sequence[str], None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """添加 quality_score 列到 spider_results 表（数据质量评分 0-100）"""
    op.add_column('spider_results', sa.Column('quality_score', sa.Float(), nullable=True))


def downgrade() -> None:
    """移除 quality_score 列"""
    op.drop_column('spider_results', 'quality_score')
