"""add spider_tasks.priority column

Revision ID: 006
Revises: 005
Create Date: 2026-08-25 18:00:00.000000

阶段 4.1 数据库变更（任务优先级）：
- spider_tasks 新增 priority 列（high/normal/low，默认 normal）+ 索引
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
# SM-EXEMPT: 历史迁移（已部署），expand-contract 检查不追溯
# expand-contract: grandfathered
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级数据库结构"""
    op.add_column(
        'spider_tasks',
        sa.Column('priority', sa.String(length=10), nullable=False, server_default='normal'),
    )
    op.create_index('ix_spider_tasks_priority', 'spider_tasks', ['priority'])


def downgrade() -> None:
    """回滚数据库结构"""
    op.drop_index('ix_spider_tasks_priority', table_name='spider_tasks')
    op.drop_column('spider_tasks', 'priority')
