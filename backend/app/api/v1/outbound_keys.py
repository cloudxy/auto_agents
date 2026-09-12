"""出站拉数钥匙 API（FR-51 / ADR-0020）：签发 / 吊销 / 本企业列表。

产品名统一「出站拉数钥匙」——不是渠道组令牌、不是平台网关钥匙。
只读（viewer）无签发/吊销控件语义 = API 拒绝 + 「请联系企业管理员」句
（GWT-51.5/51.9，控件隐藏单支）；明文只在签发响应出现一次（GWT-51.1/51.8）。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, get_current_user
from backend.app.responses import ApiResponse, created, ok
from backend.services.outbound_key_service import OutboundKeyService, require_tenant_id
from platform_core.db import get_async_db
from platform_core.schemas.outbound import (
    OutboundKeyCreate, OutboundKeyIssuedOut, OutboundKeyOut,
)

router = APIRouter()

# GWT-51.2 空态句（spec 冻结原文）：前端直接渲染，不另造第二套
EMPTY_HINT_51_2 = "还没有出站拉数钥匙。签发后才能从外部系统拉本企业结果。"
ISSUE_SUCCESS_MESSAGE = "出站拉数钥匙签发成功。明文只显示这一次，请立即复制保存。"


def _svc(session: AsyncSession = Depends(get_async_db)) -> OutboundKeyService:
    return OutboundKeyService(session)


@router.get("/keys", response_model=ApiResponse[list[OutboundKeyOut]])
async def list_keys(
    user: CurrentUser = Depends(get_current_user),
    service: OutboundKeyService = Depends(_svc),
) -> ApiResponse[list[OutboundKeyOut]]:
    tid = require_tenant_id(user.tenant_id)
    keys = await service.list_keys(tid)
    return ok(keys, message=EMPTY_HINT_51_2 if not keys else "操作成功")


@router.post("/keys", response_model=ApiResponse[OutboundKeyIssuedOut], status_code=201)
async def issue_key(
    payload: OutboundKeyCreate,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_db),
    service: OutboundKeyService = Depends(_svc),
) -> ApiResponse[OutboundKeyIssuedOut]:
    tid = require_tenant_id(user.tenant_id)
    out = await service.issue_key(tid, user.id, user.tenant_role, payload)
    await record_audit(session, user, "outbound.key.issue", f"key#{out.id}")
    return created(out, message=ISSUE_SUCCESS_MESSAGE)


@router.delete("/keys/{key_id}", response_model=ApiResponse[OutboundKeyOut])
async def revoke_key(
    key_id: int,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_db),
    service: OutboundKeyService = Depends(_svc),
) -> ApiResponse[OutboundKeyOut]:
    tid = require_tenant_id(user.tenant_id)
    out = await service.revoke_key(tid, user.tenant_role, key_id)
    await record_audit(session, user, "outbound.key.revoke", f"key#{key_id}")
    return ok(out, message="已吊销该出站拉数钥匙。")
