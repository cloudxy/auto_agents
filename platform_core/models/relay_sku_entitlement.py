"""中转 SKU 权益（FR-U20…U23 / ADR-0025）：一行 = 一企业当前中转买没买。

tenant_id NOT NULL（PIT-4）。不进 TENANT_EXEMPT。不 FK 到 relay_groups；本波不删组行。
缺行 ≡ none。专业档/企业档履约不得写本表。
"""
from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import TenantMixin


class RelaySkuEntitlement(TenantMixin, Base):
    """一企业当前中转 SKU 买没买、过没过期。"""

    __tablename__ = "relay_sku_entitlements"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uk_relay_sku_entitlements_tenant"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="代理主键")
    tenant_id = Column(
        Integer, nullable=False, comment="本企业；PIT-4 禁止 NULL=平台 SKU",
    )
    status = Column(
        String(16), nullable=False, default="none", server_default="none",
        comment="none/active/expired",
    )
    period_end = Column(
        DateTime, nullable=True,
        comment="账期结束快照。active 应用必填；expired 保留到期时刻；none 未开通 NULL",
    )
    activated_at = Column(DateTime, nullable=True, comment="最近一次进入 active。NULL=从未开通")
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
