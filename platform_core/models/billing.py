"""订阅计费：套餐 / 租户订阅 / 订单。"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import TenantMixin


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(32), nullable=False, unique=True)
    name = Column(String(64), nullable=False)
    price_cents = Column(Integer, nullable=False, default=0, server_default="0")
    period = Column(String(16), nullable=False, default="month", server_default="month")
    quota_json = Column(Text, nullable=True, comment="JSON：task_concurrency/result_storage/llm_tokens_month")
    is_public = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TenantSubscription(TenantMixin, Base):
    __tablename__ = "tenant_subscriptions"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_subscriptions_tenant"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    status = Column(String(16), nullable=False, default="active", server_default="active")
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Order(TenantMixin, Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False, default="pending", server_default="pending")
    channel = Column(String(16), nullable=False, default="offline", server_default="offline")
    idempotency_key = Column(String(64), nullable=True, unique=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
