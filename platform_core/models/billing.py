"""订阅计费：套餐 / 租户订阅 / 订单。支付通道可空（线下挂账）。"""
from sqlalchemy import (
    Column, Computed, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import TenantMixin

# 一企一商品一待支付：非终态且有商品码时生成 product_code，终态 NULL 不占坑。
OPEN_PRODUCT_SLOT_SQL = (
    "CASE WHEN product_code IS NOT NULL AND status IN "
    "('checkout_pending','paid_pending_fulfillment','pending') "
    "THEN product_code ELSE NULL END"
)


class Plan(Base):
    """平台价目（无租户列；TENANT_EXEMPT）。禁止 slug=relay。"""

    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    slug = Column(String(32), nullable=False, unique=True, comment="档位标识")
    name = Column(String(64), nullable=False, comment="展示名")
    price_cents = Column(Integer, nullable=False, default=0, server_default="0", comment="标价（分）；0=免费")
    period = Column(String(16), nullable=False, default="month", server_default="month", comment="month/year")
    quota_json = Column(Text, nullable=True, comment="JSON：task_concurrency/result_storage/llm_tokens_month")
    is_public = Column(Integer, nullable=False, default=1, server_default="1", comment="1=可下单")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(), comment="本波 ADD 表尾；R-AUD",
    )


class TenantSubscription(TenantMixin, Base):
    """当前订阅：一企业一行。"""

    __tablename__ = "tenant_subscriptions"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_subscriptions_tenant"),)

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False, comment="当前套餐")
    status = Column(String(16), nullable=False, default="active", server_default="active", comment="active/expired")
    current_period_end = Column(DateTime(timezone=True), nullable=True, comment="账期结束；免费档空")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")


class Order(TenantMixin, Base):
    """一次结账意图。新结账只写新 status；读模型双认旧 pending/paid/cancelled。"""

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("order_no", name="uk_orders_order_no"),
        UniqueConstraint("tenant_id", "open_product_slot", name="uk_orders_tenant_open_product"),
        UniqueConstraint("channel", "channel_trade_no", name="uk_orders_channel_trade"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    plan_id = Column(
        Integer, ForeignKey("plans.id"), nullable=True,
        comment="目标套餐；product_code=relay 时 NULL",
    )
    amount_cents = Column(Integer, nullable=False, comment="下单时金额快照（分）")
    status = Column(
        String(32), nullable=False, default="pending", server_default="pending",
        comment="旧 pending/paid/cancelled；新 checkout_pending/paid_pending_fulfillment/fulfilled/unpaid",
    )
    channel = Column(
        String(16), nullable=True,
        comment="alipay/wechat；NULL=W2 未选通道。禁止新写 offline",
    )
    idempotency_key = Column(String(64), nullable=True, unique=True, comment="防重复下单")
    paid_at = Column(DateTime(timezone=True), nullable=True, comment="确认收款时间")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    product_code = Column(
        String(32), nullable=True,
        comment="闭集 plan_pro/plan_enterprise/relay。NULL=040 线下单",
    )
    order_no = Column(String(64), nullable=True, comment="我方订单号。NULL=旧行")
    channel_trade_no = Column(String(64), nullable=True, comment="通道侧交易号。NULL=尚未收到")
    merchant_id_snapshot = Column(String(64), nullable=True, comment="当时商户号，不是密钥。NULL=旧线下单")
    fail_reason = Column(
        String(32), nullable=True,
        comment="cancel/timeout/channel_error/unconfigured。NULL=未失败",
    )
    late_notify_at = Column(DateTime(timezone=True), nullable=True, comment="迟到回调。NULL=从未记")
    verified_at = Column(DateTime(timezone=True), nullable=True, comment="FR-U38 通过。NULL=从未验真")
    fulfilled_at = Column(DateTime(timezone=True), nullable=True, comment="开通完成。NULL=未完成")
    unpaid_at = Column(DateTime(timezone=True), nullable=True, comment="进入 unpaid。NULL=未入该终态")
    open_product_slot = Column(
        String(32), Computed(OPEN_PRODUCT_SLOT_SQL, persisted=True),
        comment="STORED GENERATED：非终态且有商品码则为 product_code，否则 NULL",
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(), comment="本波 ADD。R-AUD",
    )
