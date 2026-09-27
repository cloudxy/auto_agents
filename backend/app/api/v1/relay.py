"""租户渠道组 SKU：组 / 令牌。平台渠道与熔断仍只在 /newapi。

T-18：列表/签发闸在权益表，不是组行 COUNT。SKU≠active → 空态句 + 去升级
product=relay；跨租户与令牌凭证失败 404 同形。明文只在当次签发。
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, get_current_user
from backend.app.responses import ApiResponse, created, ok
from backend.services.relay_service import (
    MSG_CANNOT_ISSUE, MSG_GATEWAY_UNREACHABLE, MSG_TOKENS_EMPTY, RelayService,
    is_issuer_role, require_tenant_id,
)
from backend.services.relay_sku_gate import empty_title
from platform_core.db import get_async_db
from platform_core.schemas.relay import (
    RelayGroupCreate, RelayGroupOut, RelayGroupUpdate, RelaySkuPageOut,
    RelayTokenCreate, RelayTokenOut,
)

router = APIRouter()

TOKEN_ISSUED_MESSAGE = "渠道组令牌签发成功。明文只显示这一次，请立即复制保存。"


def _svc(session: AsyncSession = Depends(get_async_db)) -> RelayService:
    return RelayService(session)


@router.get("/sku", response_model=ApiResponse[RelaySkuPageOut])
async def get_sku_page(
    user: CurrentUser = Depends(get_current_user),
    service: RelayService = Depends(_svc),
) -> ApiResponse[RelaySkuPageOut]:
    tid = require_tenant_id(user.tenant_id)
    page = await service.sku_page(tid, user.tenant_role)
    message = page.empty_title or "操作成功"
    return ok(page, message=message)


@router.get("/groups", response_model=ApiResponse[list[RelayGroupOut]])
async def list_groups(
    user: CurrentUser = Depends(get_current_user),
    service: RelayService = Depends(_svc),
) -> ApiResponse[list[RelayGroupOut]]:
    tid = require_tenant_id(user.tenant_id)
    status = await service.sku_status(tid)
    groups = await service.list_groups(tid)
    if status != "active":
        return ok(groups, message=empty_title(status))
    if not is_issuer_role(user.tenant_role):
        return ok(groups, message=MSG_CANNOT_ISSUE)
    return ok(groups)


@router.post("/groups", response_model=ApiResponse[RelayGroupOut], status_code=201)
async def create_group(
    payload: RelayGroupCreate,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_db),
    service: RelayService = Depends(_svc),
) -> ApiResponse[RelayGroupOut]:
    tid = require_tenant_id(user.tenant_id)
    out = await service.create_group(tid, user.tenant_role, payload)
    await record_audit(user, "relay.group.create", f"group#{out.id}")
    return created(out)


@router.patch("/groups/{group_id}", response_model=ApiResponse[RelayGroupOut])
async def update_group(
    group_id: int,
    payload: RelayGroupUpdate,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_db),
    service: RelayService = Depends(_svc),
) -> ApiResponse[RelayGroupOut]:
    tid = require_tenant_id(user.tenant_id)
    out = await service.update_group(tid, user.tenant_role, group_id, payload)
    await record_audit(user, "relay.group.update", f"group#{group_id}")
    return ok(out)


@router.get("/tokens", response_model=ApiResponse[list[RelayTokenOut]])
async def list_tokens(
    user: CurrentUser = Depends(get_current_user),
    service: RelayService = Depends(_svc),
) -> ApiResponse[list[RelayTokenOut]]:
    tid = require_tenant_id(user.tenant_id)
    status = await service.sku_status(tid)
    tokens = await service.list_tokens(tid)
    if status != "active":
        return ok(tokens, message=empty_title(status))
    if not tokens:
        return ok(tokens, message=MSG_TOKENS_EMPTY)
    return ok(tokens)


@router.post("/tokens", response_model=ApiResponse[RelayTokenOut], status_code=201)
async def issue_token(
    payload: RelayTokenCreate,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_db),
    service: RelayService = Depends(_svc),
) -> ApiResponse[RelayTokenOut]:
    tid = require_tenant_id(user.tenant_id)
    out = await service.issue_token(tid, user.tenant_role, payload)
    await record_audit(user, "relay.token.issue", f"token#{out.id}")
    return created(out, message=TOKEN_ISSUED_MESSAGE)


@router.get("/tokens/by-key", response_model=ApiResponse[RelayTokenOut])
async def usage_by_plaintext(
    user: CurrentUser = Depends(get_current_user),
    service: RelayService = Depends(_svc),
    x_relay_token: Optional[str] = Header(None, alias="X-Relay-Token"),
) -> ApiResponse[RelayTokenOut]:
    """令牌凭证读本企业用量。明文不回写；失败 404 同形。"""
    tid = require_tenant_id(user.tenant_id)
    out = await service.usage_by_plaintext(tid, x_relay_token or "")
    return ok(out)


@router.get("/tokens/{token_id}", response_model=ApiResponse[RelayTokenOut])
async def get_token(
    token_id: int,
    user: CurrentUser = Depends(get_current_user),
    service: RelayService = Depends(_svc),
) -> ApiResponse[RelayTokenOut]:
    """令牌详情（用量回写触发点；GWT-60.2/60.3，db-spec §12）。

    网关不可达 → 数据为本地缓存（数字不显示「已用完」），message 走
    GWT-60.5「平台 LLM 网关不可达」句族——不是套餐句。
    """
    tid = require_tenant_id(user.tenant_id)
    out, degraded = await service.get_token(tid, token_id)
    if degraded:
        return ok(out, message=MSG_GATEWAY_UNREACHABLE)
    return ok(out)


@router.post("/tokens/refresh-usage", response_model=ApiResponse[list[RelayTokenOut]])
async def refresh_token_usage(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_db),
    service: RelayService = Depends(_svc),
) -> ApiResponse[list[RelayTokenOut]]:
    """显式刷新本企业令牌用量（按页批量触发点；QA-08：列表渲染不走此面）。

    网关不可达 → 502 LLM_GATEWAY_UNREACHABLE（60.5 句族，失败可见，非套餐句）。
    """
    tid = require_tenant_id(user.tenant_id)
    tokens = await service.refresh_tokens_usage(tid)
    await record_audit(user, "relay.token.refresh_usage", f"tenant#{tid}")
    return ok(tokens, message="令牌用量已按网关最新数据刷新。")


@router.delete("/tokens/{token_id}", response_model=ApiResponse[RelayTokenOut])
async def revoke_token(
    token_id: int,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_db),
    service: RelayService = Depends(_svc),
) -> ApiResponse[RelayTokenOut]:
    tid = require_tenant_id(user.tenant_id)
    out = await service.revoke_token(tid, user.tenant_role, token_id)
    await record_audit(user, "relay.token.revoke", f"token#{token_id}")
    return ok(out, message="已吊销该渠道组令牌。")
