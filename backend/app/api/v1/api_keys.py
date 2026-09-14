"""租户自助 API Key 签发（外部数据 API）。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, require_operator
from backend.app.responses import ApiResponse, created, ok
from backend.services.api_key_service import ApiKeyService
from platform_core.db import get_async_db
from platform_core.exceptions import BusinessException
from platform_core.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyOut

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_async_db)) -> ApiKeyService:
    return ApiKeyService(session)


@router.get("", response_model=ApiResponse[list[ApiKeyOut]])
async def list_api_keys(
    user: CurrentUser = Depends(require_operator),
    service: ApiKeyService = Depends(_svc),
) -> ApiResponse[list[ApiKeyOut]]:
    if user.tenant_id is None:
        raise BusinessException("平台超管请在租户上下文中签发 Key")
    return ok(await service.list_keys(user.tenant_id))


@router.post("", response_model=ApiResponse[ApiKeyCreated], status_code=201)
async def create_api_key(
    payload: ApiKeyCreate,
    user: CurrentUser = Depends(require_operator),
    session: AsyncSession = Depends(get_async_db),
    service: ApiKeyService = Depends(_svc),
) -> ApiResponse[ApiKeyCreated]:
    if user.tenant_id is None:
        raise BusinessException("平台超管请在租户上下文中签发 Key")
    created_key = await service.create_key(user.tenant_id, payload, user.username)
    await record_audit(session, user, "api_key.create", f"key#{created_key.id}")
    return created(created_key)


@router.post("/{key_id}/revoke", response_model=ApiResponse[ApiKeyOut])
async def revoke_api_key(
    key_id: int,
    user: CurrentUser = Depends(require_operator),
    session: AsyncSession = Depends(get_async_db),
    service: ApiKeyService = Depends(_svc),
) -> ApiResponse[ApiKeyOut]:
    if user.tenant_id is None:
        raise BusinessException("平台超管请在租户上下文中签发 Key")
    out = await service.revoke(user.tenant_id, key_id)
    await record_audit(session, user, "api_key.revoke", f"key#{key_id}")
    return ok(out)
