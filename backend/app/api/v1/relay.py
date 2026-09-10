"""租户渠道组 SKU：组 / 令牌。平台渠道与熔断仍只在 /newapi。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, get_current_user
from backend.app.api.v1.members import require_tenant_manager
from backend.app.responses import ApiResponse, created, ok
from backend.services.relay_service import RelayService, require_tenant_id
from platform_core.db import get_async_db
from platform_core.schemas.relay import (
    RelayGroupCreate, RelayGroupOut, RelayGroupUpdate, RelayTokenCreate, RelayTokenOut,
)

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_async_db)) -> RelayService:
    return RelayService(session)


@router.get("/groups", response_model=ApiResponse[list[RelayGroupOut]])
async def list_groups(
    user: CurrentUser = Depends(get_current_user),
    service: RelayService = Depends(_svc),
) -> ApiResponse[list[RelayGroupOut]]:
    tid = require_tenant_id(user.tenant_id)
    return ok(await service.list_groups(tid))


@router.post("/groups", response_model=ApiResponse[RelayGroupOut], status_code=201)
async def create_group(
    payload: RelayGroupCreate,
    user: CurrentUser = Depends(require_tenant_manager),
    session: AsyncSession = Depends(get_async_db),
    service: RelayService = Depends(_svc),
) -> ApiResponse[RelayGroupOut]:
    tid = require_tenant_id(user.tenant_id)
    out = await service.create_group(tid, payload)
    await record_audit(session, user, "relay.group.create", f"group#{out.id}")
    return created(out)


@router.patch("/groups/{group_id}", response_model=ApiResponse[RelayGroupOut])
async def update_group(
    group_id: int,
    payload: RelayGroupUpdate,
    user: CurrentUser = Depends(require_tenant_manager),
    session: AsyncSession = Depends(get_async_db),
    service: RelayService = Depends(_svc),
) -> ApiResponse[RelayGroupOut]:
    tid = require_tenant_id(user.tenant_id)
    out = await service.update_group(tid, group_id, payload)
    await record_audit(session, user, "relay.group.update", f"group#{group_id}")
    return ok(out)


@router.get("/tokens", response_model=ApiResponse[list[RelayTokenOut]])
async def list_tokens(
    user: CurrentUser = Depends(get_current_user),
    service: RelayService = Depends(_svc),
) -> ApiResponse[list[RelayTokenOut]]:
    tid = require_tenant_id(user.tenant_id)
    return ok(await service.list_tokens(tid))


@router.post("/tokens", response_model=ApiResponse[RelayTokenOut], status_code=201)
async def issue_token(
    payload: RelayTokenCreate,
    user: CurrentUser = Depends(require_tenant_manager),
    session: AsyncSession = Depends(get_async_db),
    service: RelayService = Depends(_svc),
) -> ApiResponse[RelayTokenOut]:
    tid = require_tenant_id(user.tenant_id)
    out = await service.issue_token(tid, payload)
    await record_audit(session, user, "relay.token.issue", f"token#{out.id}")
    return created(out)


@router.delete("/tokens/{token_id}", response_model=ApiResponse[RelayTokenOut])
async def revoke_token(
    token_id: int,
    user: CurrentUser = Depends(require_tenant_manager),
    session: AsyncSession = Depends(get_async_db),
    service: RelayService = Depends(_svc),
) -> ApiResponse[RelayTokenOut]:
    tid = require_tenant_id(user.tenant_id)
    out = await service.revoke_token(tid, token_id)
    await record_audit(session, user, "relay.token.revoke", f"token#{token_id}")
    return ok(out)
