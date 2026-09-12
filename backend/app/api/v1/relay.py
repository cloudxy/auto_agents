"""租户渠道组 SKU：组 / 令牌。平台渠道与熔断仍只在 /newapi。

T-07（GWT-60.4/60.7）：GET 不建组（空态可达）；经办/只读无签发/吊销/停用面
——写拒绝走 Service 可见找管理员句，不挂 require_tenant_manager 的裸 403。
T-09（GWT-60.2/60.3/60.5）：令牌详情 = 用量回写触发点（网关 key info + spend
HTTP → 本地 used_tokens 缓存列；网关不可达 → 详情降级本地 + 60.5 句族 message）；
显式刷新 = 按页批量触发点（网关不可达 → 502 LLM_GATEWAY_UNREACHABLE 句族）。
列表读路径（list_tokens）只读本地列，禁止每行打网关（QA-08）。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, get_current_user
from backend.app.responses import ApiResponse, created, ok
from backend.services.relay_service import (
    MSG_CANNOT_ISSUE, MSG_GATEWAY_UNREACHABLE, MSG_TOKENS_EMPTY, RelayService,
    is_issuer_role, require_tenant_id,
)
from platform_core.db import get_async_db
from platform_core.schemas.relay import (
    RelayGroupCreate, RelayGroupOut, RelayGroupUpdate, RelayTokenCreate, RelayTokenOut,
)

router = APIRouter()

TOKEN_ISSUED_MESSAGE = "渠道组令牌签发成功。明文只显示这一次，请立即复制保存。"


def _svc(session: AsyncSession = Depends(get_async_db)) -> RelayService:
    return RelayService(session)


@router.get("/groups", response_model=ApiResponse[list[RelayGroupOut]])
async def list_groups(
    user: CurrentUser = Depends(get_current_user),
    service: RelayService = Depends(_svc),
) -> ApiResponse[list[RelayGroupOut]]:
    tid = require_tenant_id(user.tenant_id)
    groups = await service.list_groups(tid)
    # GWT-60.7：无签发权者页入口可见找管理员句（不是空表也不是裸「操作成功」）
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
    await record_audit(session, user, "relay.group.create", f"group#{out.id}")
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
    await record_audit(session, user, "relay.group.update", f"group#{group_id}")
    return ok(out)


@router.get("/tokens", response_model=ApiResponse[list[RelayTokenOut]])
async def list_tokens(
    user: CurrentUser = Depends(get_current_user),
    service: RelayService = Depends(_svc),
) -> ApiResponse[list[RelayTokenOut]]:
    tid = require_tenant_id(user.tenant_id)
    tokens = await service.list_tokens(tid)
    # GWT-60.4：无令牌空态冻结句，不是默认「暂无数据」
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
    await record_audit(session, user, "relay.token.issue", f"token#{out.id}")
    return created(out, message=TOKEN_ISSUED_MESSAGE)


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
    await record_audit(session, user, "relay.token.refresh_usage", f"tenant#{tid}")
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
    await record_audit(session, user, "relay.token.revoke", f"token#{token_id}")
    return ok(out, message="已吊销该渠道组令牌。")
