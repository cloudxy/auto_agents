"""中转上线闸：日粒度用量事实表 + 令牌网关封禁原因（审计 F3-9 / BUG-28，D19）

Revision ID: 053
Revises: 052
Create Date: 2026-09-28

- relay_usage_daily：网关 spend 日志按 (令牌, 业务日 Asia/Shanghai) 聚合；只增不减，企业月度中转用量按此求和；
- relay_tokens.blocked_reason：令牌在网关侧被 block 的原因（额度用尽 / 渠道组停用 /
  SKU 到期 / 企业月度中转额度用尽），解除条件满足时由巡检 unblock 并清空。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "053"
down_revision: Union[str, Sequence[str], None] = "052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "relay_tokens",
        sa.Column(
            "blocked_reason", sa.String(32), nullable=True,
            comment="网关侧已 block 的原因 quota_exhausted/group_disabled/sku_expired/tenant_quota；NULL=未封",
        ),
    )
    op.create_table(
        "relay_usage_daily",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, comment="主键"),
        sa.Column("tenant_id", sa.Integer(), nullable=True, comment="所属租户（NULL=平台级/未归属）"),
        sa.Column("token_id", sa.Integer(), nullable=False, comment="令牌"),
        sa.Column("stat_date", sa.Date(), nullable=False, comment="统计日（网关日志 startTime 所属的 Asia/Shanghai 业务日）"),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False, server_default="0", comment="当日 token 合计"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=True, comment="更新时间"),
        sa.ForeignKeyConstraint(["token_id"], ["relay_tokens.id"], ondelete="CASCADE",
                                name="fk_relay_usage_daily_token"),
        sa.UniqueConstraint("token_id", "stat_date", name="uq_relay_usage_daily_token_date"),
        comment="中转令牌日粒度用量事实（审计 F3-9）",
    )
    op.create_index("ix_relay_usage_daily_tenant_id", "relay_usage_daily", ["tenant_id"])
    op.create_index("ix_relay_usage_daily_token_id", "relay_usage_daily", ["token_id"])


def downgrade() -> None:
    op.drop_table("relay_usage_daily")
    op.drop_column("relay_tokens", "blocked_reason")
