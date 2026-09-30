"""users 邮箱验证：自助注册的负责人验证邮箱后企业才能用平台 LLM（决策 D21 前置闸）

Revision ID: 056
Revises: 055
Create Date: 2026-09-30

- email_verify_pending：只在企业自助注册时置 1，点验证链接后清 0。存量账号、负责人在企业内
  新建的成员都是 0（不要求验证）——判定按企业：企业负责人仍 pending 时整家企业不能用 AI 规划。
- email_verified_at：验证时刻（UTC），留档。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "056"
down_revision: Union[str, Sequence[str], None] = "055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column(
        "email_verify_pending", sa.Boolean(), nullable=False, server_default="0",
        comment="自助注册待验证邮箱（1 = 未验证；存量与成员为 0）",
    ))
    op.add_column("users", sa.Column(
        "email_verified_at", sa.DateTime(), nullable=True, comment="邮箱验证时刻（UTC）",
    ))


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email_verify_pending")
