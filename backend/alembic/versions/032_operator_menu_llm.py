"""operator 加 menu:llm（T-17 SH-11 数据回填）

Revision ID: 032
Revises: 031
Create Date: 2026-09-09

022 已 applied：只 UPDATE roles.permissions JSON，禁止改表结构。
仍不加 menu:newapi。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "032"
down_revision: Union[str, Sequence[str], None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 回填: operator.permissions JSON 追加 menu:llm（T-17 SH-11；不改表结构）
    op.execute(sa.text(
        "UPDATE roles SET permissions = JSON_ARRAY_APPEND(permissions, '$', 'menu:llm') "
        "WHERE role_key='operator' AND NOT JSON_CONTAINS(permissions, '\"menu:llm\"')"
    ))


def downgrade() -> None:
    # 回填: 去掉 operator.permissions 中的 menu:llm
    op.execute(sa.text(
        "UPDATE roles SET permissions = JSON_REMOVE("
        "permissions, JSON_UNQUOTE(JSON_SEARCH(permissions, 'one', 'menu:llm'))) "
        "WHERE role_key='operator' AND JSON_CONTAINS(permissions, '\"menu:llm\"')"
    ))
