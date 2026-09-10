"""订阅计费：套餐 / 租户订阅 / 订单。支付通道可空（线下挂账）。"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import TenantMixin


class Plan(Base):
    """平台价目（无租户列；TENANT_EXEMPT）。"""

    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    slug = Column(String(32), nullable=False, unique=True, comment="档位标识")
    name = Column(String(64), nullable=False, comment="展示名")
    price_cents = Column(Integer, nullable=False, default=0, server_default="0", comment="标价（分）；0=免费")
    period = Column(String(16), nullable=False, default="month", server_default="month", comment="month/year")
    quota_json = Column(Text, nullable=True, comment="JSON：task_concurrency/result_storage/llm_tokens_month")
    is_public = Column(Integer, nullable=False, default=1, server_default="1", comment="1=可下单")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")


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
    """升级订单。channel=offline 为现行通道；alipay/wechat 未开通。"""

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False, comment="目标套餐")
    amount_cents = Column(Integer, nullable=False, comment="下单金额（分）")
    status = Column(String(16), nullable=False, default="pending", server_default="pending", comment="pending/paid/cancelled")
    channel = Column(String(16), nullable=False, default="offline", server_default="offline", comment="offline/alipay/wechat")
    idempotency_key = Column(String(64), nullable=True, unique=True, comment="防重复下单")
    paid_at = Column(DateTime(timezone=True), nullable=True, comment="确认收款时间")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
