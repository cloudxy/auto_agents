"""add spider_definitions.source column

Revision ID: 008
Revises: e7a6f5a12bc9
Create Date: 2026-08-29 12:00:00.000000

阶段 6 数据库变更（爬虫定义来源追踪）：
- spider_definitions 新增 source 列（yml_seed/manual/ai_generated，默认 yml_seed）
- 存量行由 server_default 统一回填为 yml_seed（与种子迁移来源一致）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '008'
down_revision: Union[str, None] = 'e7a6f5a12bc9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级数据库结构"""
    op.add_column(
        'spider_definitions',
        sa.Column('source', sa.String(length=20), nullable=False,
                  server_default='yml_seed',
                  comment='来源：yml_seed/manual/ai_generated'),
    )


def downgrade() -> None:
    """回滚数据库结构"""
    op.drop_column('spider_definitions', 'source')
