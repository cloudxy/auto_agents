"""add skill_harvester spider definition (方案 A · A-P5-1)

Revision ID: 016
Revises: 015
Create Date: 2026-09-01

技能市场采集爬虫注册表登记（type=api，source=yml_seed）：
候选经 spider_results(source=marketplace) 回流，admin 候选 Tab 人工转正。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "016"
down_revision: Union[str, Sequence[str], None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """登记 skill_harvester 定义"""
    op.execute(
        sa.text(
            "INSERT INTO spider_definitions (name, title, type, description, source, enabled, created_at, updated_at) "
            "VALUES ('skill_harvester', '技能市场采集', 'api', "
            "'采集公开 skill 清单源（GitHub contents API / awesome README），"
            "候选经人工审核转正入库（方案 A P5）', 'yml_seed', 1, NOW(), NOW())"
        )
    )


def downgrade() -> None:
    """移除登记"""
    op.execute(sa.text("DELETE FROM spider_definitions WHERE name = 'skill_harvester'"))
