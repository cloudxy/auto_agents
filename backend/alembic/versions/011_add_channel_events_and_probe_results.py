"""add channel_events and channel_probe_results tables

Revision ID: 011
Revises: 010
Create Date: 2026-08-30 20:00:00.000000

阶段三 new-api 渠道集成（渠道调度器 + 真伪探针）：
- channel_events：渠道启停事件（scheduler/manual 来源；用量上下文与原因可追溯）
- channel_probe_results：真伪探针结果（10 维得分 JSON + batch 批次追溯）

纯建表迁移，可整体 downgrade 回 010。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
# SM-EXEMPT: 历史迁移（已部署），expand-contract 检查不追溯
# expand-contract: grandfathered
revision: str = '011'
down_revision: Union[str, None] = '010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级数据库结构"""
    op.create_table(
        'channel_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('channel_id', sa.BigInteger(), nullable=False, comment='new-api 渠道 ID'),
        sa.Column('action', sa.String(length=20), nullable=False, comment='动作：disabled/enabled'),
        sa.Column('usage', sa.BigInteger(), nullable=True, comment='触发时窗口用量（quota）'),
        sa.Column('limit_quota', sa.BigInteger(), nullable=True, comment='触发的用量上限'),
        sa.Column('window_hours', sa.Integer(), nullable=True, comment='统计窗口（小时）'),
        sa.Column('reason', sa.String(length=255), nullable=True, comment='原因说明'),
        sa.Column('source', sa.String(length=20), nullable=False, comment='来源：scheduler/manual'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'),
                  nullable=True, comment='创建时间'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_channel_events_created_at', 'channel_events', ['created_at'])
    op.create_index('ix_channel_events_channel_created', 'channel_events',
                    ['channel_id', 'created_at'])

    op.create_table(
        'channel_probe_results',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('channel_id', sa.BigInteger(), nullable=False, comment='new-api 渠道 ID'),
        sa.Column('model', sa.String(length=100), nullable=False, comment='被检模型名'),
        sa.Column('verdict', sa.String(length=20), nullable=False,
                  comment='判定：original/spoofed/offline'),
        sa.Column('scores', sa.JSON(), nullable=True,
                  comment='10 维探针得分与启发式指标（identity/latency/ref_similarity 等）'),
        sa.Column('latency_ms', sa.Integer(), nullable=True, comment='身份探针往返延迟（毫秒）'),
        sa.Column('batch_id', sa.String(length=64), nullable=False, comment='巡检批次（uuid hex）'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'),
                  nullable=True, comment='创建时间'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_channel_probe_results_channel_created', 'channel_probe_results',
                    ['channel_id', 'created_at'])
    op.create_index('ix_channel_probe_results_batch_id', 'channel_probe_results', ['batch_id'])


def downgrade() -> None:
    """回滚数据库结构"""
    op.drop_index('ix_channel_probe_results_batch_id', table_name='channel_probe_results')
    op.drop_index('ix_channel_probe_results_channel_created', table_name='channel_probe_results')
    op.drop_table('channel_probe_results')
    op.drop_index('ix_channel_events_channel_created', table_name='channel_events')
    op.drop_index('ix_channel_events_created_at', table_name='channel_events')
    op.drop_table('channel_events')
