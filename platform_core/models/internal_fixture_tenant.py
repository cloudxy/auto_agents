"""内部测试企业名单（FR-U03）：一行 = 一家当前在夹具名单上的企业。

超管加入 INSERT、移出 DELETE。tenant_id 是主语不是隔离归属；禁止 TenantMixin。
同 PR 登记 TENANT_EXEMPT_TABLES（PIT-3）。不加软删、不加 tenants FK。
"""
from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from platform_core.models.base import Base


class InternalFixtureTenant(Base):
    """当前在内部测试名单上的企业（移出即物理删除）"""

    __tablename__ = "internal_fixture_tenants"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uk_internal_fixture_tenants_tenant"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="代理主键，跟仓 INT")
    tenant_id = Column(Integer, nullable=False, comment="被标为夹具的企业；PIT-4 禁止 NULL=平台")
    created_by = Column(String(64), nullable=False, comment="谁标的（超管用户名快照，无用户 FK）")
    created_at = Column(
        DateTime, nullable=False, server_default=func.current_timestamp(), comment="何时标上",
    )
    updated_at = Column(
        DateTime, nullable=False, server_default=func.current_timestamp(),
        comment="R-AUD；移出为 DELETE",
    )

    def __repr__(self) -> str:
        return f"<InternalFixtureTenant tenant={self.tenant_id}>"
