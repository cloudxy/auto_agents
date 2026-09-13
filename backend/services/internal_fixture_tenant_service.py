"""夹具企业名单：超管加入/移出；唯一键兜底，禁止只先查后插。"""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.internal_fixture_tenant_repository import (
    InternalFixtureTenantRepository,
)
from platform_core.logger import get_logger
from platform_core.schemas.internal_fixture_tenant import (
    InternalFixtureTenantListOut,
    InternalFixtureTenantOut,
)

logger = get_logger("api")


class InternalFixtureTenantService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = InternalFixtureTenantRepository(session)

    async def list_all(self) -> InternalFixtureTenantListOut:
        logger.info("列出夹具企业名单")
        rows = await self.repo.list_recent()
        return InternalFixtureTenantListOut(
            total=len(rows),
            items=[InternalFixtureTenantOut.model_validate(r) for r in rows],
        )

    async def add(self, tenant_id: int, created_by: str) -> InternalFixtureTenantOut:
        logger.info(f"加入夹具名单 | tenant={tenant_id}")
        try:
            row = await self.repo.create(tenant_id=tenant_id, created_by=created_by)
            out = InternalFixtureTenantOut.model_validate(row)
            await self.session.commit()
            return out
        except IntegrityError:
            await self.session.rollback()
            existing = await self.repo.get_by_tenant_id(tenant_id)
            if existing is None:
                raise
            logger.info(f"夹具名单已存在 | tenant={tenant_id}")
            return InternalFixtureTenantOut.model_validate(existing)

    async def remove(self, tenant_id: int) -> None:
        logger.info(f"移出夹具名单 | tenant={tenant_id}")
        await self.repo.delete_by_tenant_id(tenant_id)
        await self.session.commit()
