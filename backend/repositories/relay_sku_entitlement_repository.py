"""中转 SKU 权益仓储：点查 + T-17 履约写入。读路径仍缺行 ≡ none。"""
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.relay_sku_entitlement import RelaySkuEntitlement
from platform_core.repository import BaseRepository


class RelaySkuEntitlementRepository(BaseRepository[RelaySkuEntitlement]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=RelaySkuEntitlement, session=session)

    async def get_by_tenant_id(self, tenant_id: int) -> Optional[RelaySkuEntitlement]:
        stmt = select(RelaySkuEntitlement).where(
            RelaySkuEntitlement.tenant_id == tenant_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def activate_for_tenant(
        self, tenant_id: int, *, period_end: datetime, activated_at: datetime,
    ) -> None:
        row = await self.get_by_tenant_id(tenant_id)
        if row is None:
            await self.create(
                tenant_id=tenant_id, status="active",
                period_end=period_end, activated_at=activated_at,
            )
            return
        row.status = "active"
        row.period_end = period_end
        row.activated_at = activated_at
        await self.session.flush()
