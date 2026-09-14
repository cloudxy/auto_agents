"""plans/orders/subscriptions + tenant relay groups/tokens

Revision ID: 040
Revises: 039
Create Date: 2026-09-10

Wave 2/3 骨架：线下挂账；租户渠道组。禁止复活 028/029/030。
在线支付通道未接线。不开 LLM.ENABLED。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "040"
down_revision: Union[str, Sequence[str], None] = "039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("plans"):
        _create_plans()
    if not _has_table("tenant_subscriptions"):
        _create_subscriptions()
    if not _has_table("orders"):
        _create_orders()
    if not _has_table("relay_groups"):
        _create_relay_groups()
    if not _has_table("relay_tokens"):
        _create_relay_tokens()
    _seed_plans()
    _grant_relay_menu()


def _create_plans() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("slug", sa.String(length=32), nullable=False, comment="档位标识"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="展示名"),
        sa.Column("price_cents", sa.Integer(), nullable=False, server_default="0", comment="标价（分）；0=免费"),
        sa.Column("period", sa.String(length=16), nullable=False, server_default="month", comment="month/year"),
        sa.Column("quota_json", sa.Text(), nullable=True, comment="JSON 配额"),
        sa.Column("is_public", sa.Integer(), nullable=False, server_default="1", comment="1=可下单"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), comment="创建时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )


def _create_subscriptions() -> None:
    op.create_table(
        "tenant_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("tenant_id", sa.Integer(), nullable=True, comment="所属租户"),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=False, comment="当前套餐"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active", comment="active/expired"),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True, comment="账期结束"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_subscriptions_tenant"),
    )
    op.create_index("ix_tenant_subscriptions_tenant_id", "tenant_subscriptions", ["tenant_id"])


def _create_orders() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("tenant_id", sa.Integer(), nullable=True, comment="所属租户"),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=False, comment="目标套餐"),
        sa.Column("amount_cents", sa.Integer(), nullable=False, comment="下单金额（分）"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending", comment="pending/paid/cancelled"),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="offline", comment="offline/alipay/wechat"),
        sa.Column("idempotency_key", sa.String(length=64), nullable=True, comment="防重复下单"),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True, comment="确认收款时间"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), comment="创建时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_orders_tenant_id", "orders", ["tenant_id"])


def _create_relay_groups() -> None:
    op.create_table(
        "relay_groups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("tenant_id", sa.Integer(), nullable=True, comment="所属租户"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="组名，企业内唯一"),
        sa.Column("rpm_limit", sa.Integer(), nullable=False, server_default="0", comment="每分钟请求上限；0=不限"),
        sa.Column("tpm_limit", sa.Integer(), nullable=False, server_default="0", comment="每分钟 token 上限；0=不限"),
        sa.Column("models_json", sa.JSON(), nullable=True, comment="可用模型 id 列表"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="enabled", comment="enabled/disabled"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_relay_groups_tenant_name"),
    )
    op.create_index("ix_relay_groups_tenant_id", "relay_groups", ["tenant_id"])


def _create_relay_tokens() -> None:
    op.create_table(
        "relay_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("tenant_id", sa.Integer(), nullable=True, comment="所属租户"),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("relay_groups.id"), nullable=False, comment="所属渠道组"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="令牌备注名"),
        sa.Column("key_prefix", sa.String(length=16), nullable=False, comment="展示前缀"),
        sa.Column("key_hash", sa.String(length=64), nullable=False, comment="SHA-256 指纹"),
        sa.Column("quota_tokens", sa.Integer(), nullable=False, server_default="-1", comment="额度；-1=不限"),
        sa.Column("used_tokens", sa.Integer(), nullable=False, server_default="0", comment="已用 token"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True, comment="过期"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True, comment="吊销时间"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True, comment="最近使用"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), comment="创建时间"),
        sa.Column("note", sa.Text(), nullable=True, comment="备注"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index("ix_relay_tokens_tenant_id", "relay_tokens", ["tenant_id"])


def _seed_plans() -> None:
    # 回填: 免费档（与 029 双线会合时 slug 可能已在）
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


def _grant_relay_menu() -> None:
    # 回填: 租户角色可见渠道组菜单
    op.execute(sa.text(
        "UPDATE roles SET permissions = JSON_ARRAY_APPEND(permissions, '$', 'menu:relay') "
        "WHERE role_key IN ('viewer','operator','admin') "
        "AND NOT JSON_CONTAINS(permissions, '\"menu:relay\"')"
    ))


def downgrade() -> None:
    op.drop_index("ix_relay_tokens_tenant_id", table_name="relay_tokens")
    op.drop_table("relay_tokens")
    op.drop_index("ix_relay_groups_tenant_id", table_name="relay_groups")
    op.drop_table("relay_groups")
    op.drop_index("ix_orders_tenant_id", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_tenant_subscriptions_tenant_id", table_name="tenant_subscriptions")
    op.drop_table("tenant_subscriptions")
    op.drop_table("plans")
