"""seed flow_generic spider definition

Revision ID: 007
Revises: 006
Create Date: 2026-08-25 19:00:00.000000

阶段 5.1 数据库变更（流程化采集引擎）：
- spider_definitions 登记 flow_generic（type=custom，与 config/default/spiders.yml 同步）
- 幂等：已存在同名定义时跳过插入
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级数据库结构"""
    definitions = sa.table(
        'spider_definitions',
        sa.column('name', sa.String),
        sa.column('title', sa.String),
        sa.column('type', sa.String),
        sa.column('description', sa.Text),
        sa.column('enabled', sa.Boolean),
    )
    connection = op.get_bind()
    exists = connection.execute(
        sa.text("SELECT id FROM spider_definitions WHERE name = 'flow_generic'")
    ).fetchone()
    if exists is None:
        op.bulk_insert(definitions, [
            {'name': 'flow_generic', 'title': '流程化采集（分页/详情/过滤）', 'type': 'custom',
             'description': '按流程定义采集：列表字段 + 自动翻页 + 详情页二次采集 + 条件过滤', 'enabled': True},
        ])


def downgrade() -> None:
    """回滚数据库结构"""
    op.execute("DELETE FROM spider_definitions WHERE name = 'flow_generic'")
