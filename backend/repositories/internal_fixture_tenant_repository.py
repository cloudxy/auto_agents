"""夹具企业名单仓储（按 tenant_id 点查 / 物理删除）"""
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.internal_fixture_tenant import InternalFixtureTenant
from platform_core.repository import BaseRepository


class InternalFixtureTenantRepository(BaseRepository[InternalFixtureTenant]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=InternalFixtureTenant, session=session)

    async def get_by_tenant_id(self, tenant_id: int) -> Optional[InternalFixtureTenant]:
        stmt = select(InternalFixtureTenant).where(InternalFixtureTenant.tenant_id == tenant_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_recent(self, *, skip: int = 0, limit: int = 500) -> list[InternalFixtureTenant]:
        stmt = (
            select(InternalFixtureTenant)
            .order_by(InternalFixtureTenant.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete_by_tenant_id(self, tenant_id: int) -> int:
        stmt = delete(InternalFixtureTenant).where(InternalFixtureTenant.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)
