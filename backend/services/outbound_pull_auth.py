"""出站拉数鉴权收口（FR-M20 / [SEC-2]）：只认出站钥匙；错平面事件无明文。"""
from __future__ import annotations

import hashlib
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.external_api.v1.webhooks import bound_tenant_id
from backend.services.api_key_service import ApiKeyService
from backend.services.product_event_service import emit_product_event
from platform_core.logger import get_logger
from platform_core.models.relay import RelayToken

logger = get_logger("service.outbound_pull")


async def guess_reject_tenant(session: AsyncSession, api_key: str) -> Optional[int]:
    """错平面归因：只为事件带 tenant_id，不授权拉数。明文不入日志。"""
    logger.info("出站拉数拒绝归因")
    if not api_key:
        return None
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    if api_key.startswith("sk-"):
        row = (await session.execute(
            select(RelayToken.tenant_id).where(RelayToken.key_hash == digest)
        )).scalar_one_or_none()
        if row is not None:
            return int(row)
    tid = await ApiKeyService(session).authenticate(api_key)
    if tid is not None:
        return int(tid)
    bound = bound_tenant_id(api_key)
    return int(bound) if bound is not None else None


async def record_wrong_plane_rejected(session: AsyncSession, api_key: str) -> None:
    """上报 outbound_wrong_plane_rejected；失败不挡（emit 自吞）。"""
    logger.warning("出站拉数鉴权拒绝 | 链=仅出站钥匙表未命中")
    tid = await guess_reject_tenant(session, api_key)
    await emit_product_event(
        session, "outbound_wrong_plane_rejected",
        tenant_id=tid,
        props={"reason": "wrong_plane", "tenant_id": tid},
    )
