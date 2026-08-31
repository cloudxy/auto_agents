"""add task retry/started columns and spider_schedules table

Revision ID: 003
Revises: 002
Create Date: 2026-08-25 00:00:00.000000

阶段 1 数据库变更：
- spider_tasks 增加 retry_count（失败自动重试计数）与 started_at（运行起始时刻）
- 新增 spider_schedules 表（定时调度计划，对标 Crawlab 定时任务）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002a'  # 基线修复(E0.2)：spider_tasks 基线表插在 003 之前
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级数据库结构"""
    op.add_column('spider_tasks', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('spider_tasks', sa.Column('started_at', sa.DateTime(), nullable=True))

    op.create_table(
        'spider_schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('spider_name', sa.String(length=100), nullable=False),
        sa.Column('cron_expr', sa.String(length=100), nullable=False),
        sa.Column('params', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.Column('next_run_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_spider_schedules_id'), 'spider_schedules', ['id'], unique=False)
    op.create_index(op.f('ix_spider_schedules_spider_name'), 'spider_schedules', ['spider_name'], unique=False)
    op.create_index(op.f('ix_spider_schedules_next_run_at'), 'spider_schedules', ['next_run_at'], unique=False)


def downgrade() -> None:
    """降级数据库结构"""
    op.drop_index(op.f('ix_spider_schedules_next_run_at'), table_name='spider_schedules')
    op.drop_index(op.f('ix_spider_schedules_spider_name'), table_name='spider_schedules')
    op.drop_index(op.f('ix_spider_schedules_id'), table_name='spider_schedules')
    op.drop_table('spider_schedules')
    op.drop_column('spider_tasks', 'started_at')
    op.drop_column('spider_tasks', 'retry_count')
