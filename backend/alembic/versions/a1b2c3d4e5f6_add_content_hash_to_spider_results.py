"""add content_hash to spider_results

Revision ID: a1b2c3d4e5f6
Revises: 8551b2c539b2
Create Date: 2026-08-26 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
# SM-EXEMPT: 历史迁移（已部署），expand-contract 检查不追溯
# expand-contract: grandfathered
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '8551b2c539b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """添加 content_hash 列 + 索引到 spider_results 表（增量去重）"""
    op.add_column('spider_results', sa.Column('content_hash', sa.String(32), nullable=True))
    op.create_index(op.f('ix_spider_results_content_hash'), 'spider_results', ['content_hash'], unique=False)


def downgrade() -> None:
    """移除 content_hash 列及索引"""
    op.drop_index(op.f('ix_spider_results_content_hash'), table_name='spider_results')
    op.drop_column('spider_results', 'content_hash')
