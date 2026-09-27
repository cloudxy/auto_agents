"""N3 结账单据 expand + 商户凭据 + 中转 SKU 权益（T-14 / FR-U30 U31 U33 U38 U20）

Revision ID: 046
Revises: 045
Create Date: 2026-09-12

upgrade-four-pillars T-14：orders 加列/放宽/生成列唯一；
payment_channel_credentials、relay_sku_entitlements 新表。
expand-contract：status VARCHAR 16->32；plan_id 放宽可空；新列一期可空。
禁止本文件改 internal_fixture_tenants / 夹具快照（N1=045）。
禁止 DROP relay_groups。禁止复活 028/029/030。
生成列表达式 ORM 同源：platform_core.models.billing.OPEN_PRODUCT_SLOT_SQL
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "046"
down_revision: Union[str, Sequence[str], None] = "045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OPEN_SLOT = (
    "CASE WHEN product_code IS NOT NULL AND status IN "
    "('checkout_pending','paid_pending_fulfillment','pending') "
    "THEN product_code ELSE NULL END"
)

_DT = sa.DateTime(timezone=True)
_NAIVE = sa.DateTime()


def upgrade() -> None:
    _widen_orders()
    _add_order_tail_columns()
    _add_open_product_slot_and_uniques()
    _create_payment_channel_credentials()
    _create_relay_sku_entitlements()
    op.add_column(
        "plans",
        sa.Column(
            "updated_at", _DT, nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="本波 ADD 表尾；R-AUD",
        ),
    )


def downgrade() -> None:
    op.drop_column("plans", "updated_at")
    op.drop_table("relay_sku_entitlements")
    op.drop_table("payment_channel_credentials")
    _drop_order_uniques_and_generated()
    _drop_order_tail_columns()
    _restore_orders_legacy()


def _widen_orders() -> None:
    op.alter_column(
        "orders", "status",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
        existing_server_default=sa.text("'pending'"),
        comment="旧 pending/paid/cancelled；新 checkout_pending/paid_pending_fulfillment/fulfilled/unpaid",
    )
    op.alter_column(
        "orders", "plan_id",
        existing_type=sa.Integer(),
        nullable=True,
        existing_nullable=False,
        comment="目标套餐；product_code=relay 时 NULL",
    )


def _add_order_tail_columns() -> None:
    op.add_column("orders", sa.Column(
        "product_code", sa.String(32), nullable=True,
        comment="闭集 plan_pro/plan_enterprise/relay。NULL=040 线下单",
    ))
    op.add_column("orders", sa.Column(
        "order_no", sa.String(64), nullable=True, comment="我方订单号。NULL=旧行",
    ))
    op.add_column("orders", sa.Column(
        "channel_trade_no", sa.String(64), nullable=True,
        comment="通道侧交易号。NULL=尚未收到",
    ))
    op.add_column("orders", sa.Column(
        "merchant_id_snapshot", sa.String(64), nullable=True,
        comment="当时商户号，不是密钥。NULL=旧线下单",
    ))
    op.add_column("orders", sa.Column(
        "fail_reason", sa.String(32), nullable=True,
        comment="cancel/timeout/channel_error/unconfigured。NULL=未失败",
    ))
    op.add_column("orders", sa.Column(
        "late_notify_at", _DT, nullable=True, comment="迟到回调。NULL=从未记",
    ))
    op.add_column("orders", sa.Column(
        "verified_at", _DT, nullable=True, comment="FR-U38 通过。NULL=从未验真",
    ))
    op.add_column("orders", sa.Column(
        "fulfilled_at", _DT, nullable=True, comment="开通完成。NULL=未完成",
    ))
    op.add_column("orders", sa.Column(
        "unpaid_at", _DT, nullable=True, comment="进入 unpaid。NULL=未入该终态",
    ))


def _add_open_product_slot_and_uniques() -> None:
    op.add_column("orders", sa.Column(
        "open_product_slot", sa.String(32),
        sa.Computed(_OPEN_SLOT, persisted=True),
        comment="STORED GENERATED：非终态且有商品码则为 product_code，否则 NULL",
    ))
    op.add_column("orders", sa.Column(
        "updated_at", _DT, nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"), comment="本波 ADD。R-AUD",
    ))
    op.create_unique_constraint("uk_orders_order_no", "orders", ["order_no"])
    op.create_unique_constraint(
        "uk_orders_tenant_open_product", "orders", ["tenant_id", "open_product_slot"],
    )
    op.create_unique_constraint(
        "uk_orders_channel_trade", "orders", ["channel", "channel_trade_no"],
    )


def _create_payment_channel_credentials() -> None:
    op.create_table(
        "payment_channel_credentials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="代理主键"),
        sa.Column("channel", sa.String(16), nullable=False, comment="alipay/wechat；一通道一行"),
        sa.Column("merchant_no", sa.String(64), nullable=False, comment="商户号，可掩码；不是密钥"),
        sa.Column(
            "secrets_encrypted", sa.Text(), nullable=False,
            comment="不透明密文 blob。明文永不落库/git/yml/浏览器/日志/Redis",
        ),
        sa.Column(
            "key_version", sa.Integer(), nullable=False, server_default="1",
            comment="每轮换 +1；旧密文不保留",
        ),
        sa.Column("rotated_at", _NAIVE, nullable=True, comment="NULL=从未轮换"),
        sa.Column("created_by", sa.String(64), nullable=True, comment="超管用户名"),
        sa.Column("updated_by", sa.String(64), nullable=True),
        sa.Column("created_at", _NAIVE, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", _NAIVE, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel", name="uk_payment_channel_credentials_channel"),
    )


def _create_relay_sku_entitlements() -> None:
    op.create_table(
        "relay_sku_entitlements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="代理主键"),
        sa.Column(
            "tenant_id", sa.Integer(), nullable=False,
            comment="本企业；PIT-4 禁止 NULL=平台 SKU",
        ),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="none",
            comment="none/active/expired",
        ),
        sa.Column(
            "period_end", _NAIVE, nullable=True,
            comment="账期结束快照。active 应用必填；expired 保留到期时刻；none 未开通 NULL",
        ),
        sa.Column(
            "activated_at", _NAIVE, nullable=True,
            comment="最近一次进入 active。NULL=从未开通",
        ),
        sa.Column("created_at", _NAIVE, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", _NAIVE, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uk_relay_sku_entitlements_tenant"),
    )


def _drop_order_uniques_and_generated() -> None:
    op.drop_constraint("uk_orders_channel_trade", "orders", type_="unique")
    op.drop_constraint("uk_orders_tenant_open_product", "orders", type_="unique")
    op.drop_constraint("uk_orders_order_no", "orders", type_="unique")
    op.drop_column("orders", "open_product_slot")


def _drop_order_tail_columns() -> None:
    for col in (
        "updated_at", "unpaid_at", "fulfilled_at", "verified_at", "late_notify_at",
        "fail_reason", "merchant_id_snapshot", "channel_trade_no", "order_no",
        "product_code",
    ):
        op.drop_column("orders", col)


def _restore_orders_legacy() -> None:
    # 回填: down 收紧前把新字面量映回旧值（expand-contract 逆向）
    op.execute(sa.text(
        "UPDATE orders SET status = CASE "
        "WHEN status IN ('checkout_pending','paid_pending_fulfillment') THEN 'pending' "
        "WHEN status = 'fulfilled' THEN 'paid' "
        "WHEN status = 'unpaid' THEN 'cancelled' "
        "ELSE status END"
    ))
    op.execute(sa.text(
        "UPDATE orders SET plan_id = (SELECT id FROM plans WHERE slug = 'pro' LIMIT 1) "
        "WHERE plan_id IS NULL"
    ))
    op.alter_column(
        "orders", "plan_id",
        existing_type=sa.Integer(),
        nullable=False,
        existing_nullable=True,
        comment="目标套餐",
    )
    op.alter_column(
        "orders", "status",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
        existing_server_default=sa.text("'pending'"),
        comment="pending/paid/cancelled",
    )
