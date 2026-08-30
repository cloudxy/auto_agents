"""add spider_definitions table with seed rows

Revision ID: 005
Revises: 004
Create Date: 2026-08-25 16:30:00.000000

阶段 3.3 数据库变更（爬虫注册表迁库）：
- 新增 spider_definitions 表（承接 config/default/spiders.yml 的 SPIDERS 元数据）
- 种子行与 yml 当前登记保持一致（yml 保留为配置兜底）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级数据库结构"""
    op.create_table(
        'spider_definitions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=100), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False, server_default='web'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index('ix_spider_definitions_name', 'spider_definitions', ['name'])

    # 种子数据：与 config/default/spiders.yml 的 SPIDERS 保持一致
    definitions = sa.table(
        'spider_definitions',
        sa.column('name', sa.String),
        sa.column('title', sa.String),
        sa.column('type', sa.String),
        sa.column('description', sa.Text),
        sa.column('enabled', sa.Boolean),
    )
    op.bulk_insert(definitions, [
        {'name': 'example', 'title': '通用采集示例', 'type': 'web',
         'description': '多模式演示爬虫：自动识别 JSON/HTML 内容类型', 'enabled': True},
        {'name': 'openweather', 'title': 'OpenWeather 天气接口', 'type': 'api',
         'description': '采集全球城市实时天气（需在配置中心配置 API Key）', 'enabled': True},
        {'name': 'dianping_home', 'title': '大众点评首页', 'type': 'web',
         'description': '高风控站点采集演示（需代理与会话保持）', 'enabled': True},
        {'name': 'zhihu_feed', 'title': '知乎推荐流', 'type': 'web',
         'description': '知乎推荐页内容采集（需登录态）', 'enabled': True},
        {'name': 'generic', 'title': '自定义采集（免代码）', 'type': 'custom',
         'description': '按页面地址 + 选择器规则采集任意站点，无需编写爬虫代码', 'enabled': True},
    ])


def downgrade() -> None:
    """回滚数据库结构"""
    op.drop_index('ix_spider_definitions_name', table_name='spider_definitions')
    op.drop_table('spider_definitions')
