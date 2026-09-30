"""users.token_version：重置密码即吊销已签发的会话（审计 QA-B1-12）

Revision ID: 054
Revises: 053
Create Date: 2026-09-28

JWT 携带签发时的 tv；鉴权时与库内 token_version 比对，不等即 401。重置密码时 +1，
账号被盗后「重置密码」能把攻击者手里的旧令牌立刻踢掉（原先要等令牌自然过期）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "054"
down_revision: Union[str, Sequence[str], None] = "053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "token_version", sa.Integer(), nullable=False, server_default="0",
            comment="会话版本：重置密码 +1，旧令牌 tv 不等即失效",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
