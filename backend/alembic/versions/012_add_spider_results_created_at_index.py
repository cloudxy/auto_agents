"""add spider_results created_at and spider_name+created_at indexes

Revision ID: 012
Revises: 011
Create Date: 2026-08-30 21:00:00.000000

期3数据层优化（spider_results 查询索引补齐）：
- ix_spider_results_created_at：Data 页 created_at 倒序 + offset/limit 分页、
  daily_result_counts 的 created_at >= since 范围聚合
- ix_spider_results_spider_created：(spider_name, created_at) 复合索引，
  数据中心按爬虫名过滤后按采集时间倒序分页

MySQL 在线 DDL 说明：
- op.create_index 生成 CREATE INDEX 语句，MySQL 8.0 对二级索引默认
  ALGORITHM=INPLACE、LOCK=NONE，允许并发读写（不锁表）。
- 建议：行数上百万的表请在业务低峰期执行，避免与大批量写入叠加造成 IO 压力；
  如需显式声明可手工执行
  ALTER TABLE spider_results ADD INDEX ... ALGORITHM=INPLACE, LOCK=NONE。

纯索引迁移，可整体 downgrade 回 011（不触碰表数据）。
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '012'
down_revision: Union[str, None] = '011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级数据库结构：为 spider_results 补齐时间维度查询索引（在线 DDL，不锁表）"""
    op.create_index(
        'ix_spider_results_created_at', 'spider_results', ['created_at'], unique=False
    )
    op.create_index(
        'ix_spider_results_spider_created',
        'spider_results',
        ['spider_name', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    """回滚数据库结构：移除本次新增的两个索引"""
    op.drop_index('ix_spider_results_spider_created', table_name='spider_results')
    op.drop_index('ix_spider_results_created_at', table_name='spider_results')
