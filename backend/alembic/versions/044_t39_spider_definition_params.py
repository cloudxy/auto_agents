"""spider_definitions 加定义参数列（params JSON，expand-only）——FR-103 / T-39

Revision ID: 044
Revises: 043
Create Date: 2026-09-11

feat-product-complete T-39（contract §11 / spec FR-103 GWT-103.1）：
- 方案编辑面扩容：api 型定义参数（urls/headers，字段集源自 yml SPIDER_TYPES.api.fields）
  落本表 params；flow 型镜像注册来源 ai_plans.generated_params；代码型恒 NULL。
- 入队未带 params 时取定义参数 → 编辑保存后对后续任务生效（在跑任务快照不受影响）。
- 纯加列（expand-only，无破坏性变更，存量行 NULL=无定义参数）；down = drop column。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "044"
down_revision: Union[str, Sequence[str], None] = "043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "spider_definitions",
        sa.Column(
            "params", sa.JSON(), nullable=True,
            comment="定义参数（T-39/FR-103）：api 型默认任务参数（urls/headers）；"
                    "flow 型镜像注册来源计划的 generated_params；代码型恒 NULL",
        ),
    )


def downgrade() -> None:
    op.drop_column("spider_definitions", "params")
