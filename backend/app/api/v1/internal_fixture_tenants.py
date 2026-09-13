"""超管维护内部测试企业名单。非超管 404 同形。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import CurrentUser, require_platform_admin_or_404
from backend.app.responses import ok
from backend.services.internal_fixture_tenant_service import InternalFixtureTenantService
from platform_core.db import get_async_db
from platform_core.logger import get_logger
from platform_core.schemas.internal_fixture_tenant import InternalFixtureTenantCreate

logger = get_logger("api")

router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> InternalFixtureTenantService:
    return InternalFixtureTenantService(session)


@router.get("")
async def list_internal_fixture_tenants(
    _user: CurrentUser = Depends(require_platform_admin_or_404),
    service: InternalFixtureTenantService = Depends(_service),
):
    logger.info(f"超管列出夹具名单 | user={_user.username}")
    data = await service.list_all()
    return ok(data=data.model_dump(mode="json"))


@router.post("")
async def add_internal_fixture_tenant(
    body: InternalFixtureTenantCreate,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    service: InternalFixtureTenantService = Depends(_service),
):
    logger.info(f"超管加入夹具名单 | user={user.username} tenant={body.tenant_id}")
    data = await service.add(body.tenant_id, user.username)
    return ok(data=data.model_dump(mode="json"))


@router.delete("/{tenant_id}")
async def remove_internal_fixture_tenant(
    tenant_id: int,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    service: InternalFixtureTenantService = Depends(_service),
):
    logger.info(f"超管移出夹具名单 | user={user.username} tenant={tenant_id}")
    await service.remove(tenant_id)
    return ok(data={"tenant_id": tenant_id, "removed": True})
