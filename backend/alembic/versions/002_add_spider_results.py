"""add spider_results table

Revision ID: 002
Revises: 001
Create Date: 2026-08-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
# SM-EXEMPT: 历史迁移（已部署），expand-contract 检查不追溯
# expand-contract: grandfathered
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级数据库结构：新增爬虫结果表"""
    op.create_table(
        'spider_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('spider_name', sa.String(length=100), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=True),
        sa.Column('item_type', sa.String(length=100), nullable=True),
        sa.Column('extra', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_spider_results_id'), 'spider_results', ['id'], unique=False)
    op.create_index(op.f('ix_spider_results_task_id'), 'spider_results', ['task_id'], unique=False)
    op.create_index(op.f('ix_spider_results_spider_name'), 'spider_results', ['spider_name'], unique=False)


def downgrade() -> None:
    """降级数据库结构"""
    op.drop_index(op.f('ix_spider_results_spider_name'), table_name='spider_results')
    op.drop_index(op.f('ix_spider_results_task_id'), table_name='spider_results')
    op.drop_index(op.f('ix_spider_results_id'), table_name='spider_results')
    op.drop_table('spider_results')
