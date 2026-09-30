"""plans/subscriptions/orders + llm cost columns

Revision ID: 029
Revises: 028
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "029"
down_revision: Union[str, Sequence[str], None] = "028"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_column(table: str, col: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return col in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_table("plans"):
        _create_billing_tables()
        _seed_plans()
    if not _has_column("llm_providers", "unit_price_per_1k_cents"):
        op.add_column("llm_providers", sa.Column(
            "unit_price_per_1k_cents", sa.Integer(), nullable=True, comment="每千 token 单价（分）"
        ))
    if not _has_column("llm_token_usage", "cost_cents"):
        op.add_column("llm_token_usage", sa.Column(
            "cost_cents", sa.BigInteger(), nullable=False, server_default="0"
        ))


def _create_billing_tables() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(32), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period", sa.String(16), nullable=False, server_default="month"),
        sa.Column("quota_json", sa.Text(), nullable=True),
        sa.Column("is_public", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "tenant_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_subscriptions_tenant"),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("channel", sa.String(16), nullable=False, server_default="offline"),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )


def _seed_plans() -> None:
    # 回填: 免费档/专业档价目（JSON 走 bindparams，避免 :5 被当成 SQL bind）
    op.execute(
        sa.text(
            "INSERT INTO plans (slug, name, price_cents, period, quota_json, is_public) "
            "SELECT 'free', '免费档', 0, 'month', :q_free, 1 FROM DUAL "
            "WHERE NOT EXISTS (SELECT 1 FROM plans WHERE slug = 'free')"
        ).bindparams(
            q_free='{"task_concurrency":5,"result_storage":10000,"llm_tokens_month":200000}',
        )
    )
    # 回填: 专业档
    op.execute(
        sa.text(
            "INSERT INTO plans (slug, name, price_cents, period, quota_json, is_public) "
            "SELECT 'pro', '专业档', 29900, 'month', :q_pro, 1 FROM DUAL "
            "WHERE NOT EXISTS (SELECT 1 FROM plans WHERE slug = 'pro')"
        ).bindparams(
            q_pro='{"task_concurrency":20,"result_storage":500000,"llm_tokens_month":5000000}',
        )
    )


def downgrade() -> None:
    # 审计 BUG-42：plans / tenant_subscriptions / orders 与 040 分支共用（两边 upgrade 都是
    # 「不存在才建」）。穿过 048 merge 降级时本分支先跑，原先无条件删表，040→047 分支随后
    # 找不到 orders 而失败。040 分支在（relay_groups 存在）时由 040 负责删表，这里只撤本迁移独有的列。
    if _has_column("llm_token_usage", "cost_cents"):
        op.drop_column("llm_token_usage", "cost_cents")
    if _has_column("llm_providers", "unit_price_per_1k_cents"):
        op.drop_column("llm_providers", "unit_price_per_1k_cents")
    if _has_table("relay_groups"):
        return
    for table in ("orders", "tenant_subscriptions", "plans"):
        if _has_table(table):
            op.drop_table(table)
