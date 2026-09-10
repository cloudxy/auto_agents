"""市场蓝图事件投递（T-32）。失败不挡主路径；查询面仍走 T-12 超管 API。"""
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.product_event_service import emit_product_event
from platform_core.logger import get_logger

logger = get_logger("api")

MARKET_SUBSCRIBE_SUCCEEDED = "market_subscribe_succeeded"
MARKET_SUBSCRIBE_REJECTED = "market_subscribe_rejected"
MARKET_LIST_VIEWED = "market_list_viewed"
MARKET_SEARCH_SUBMITTED = "market_search_submitted"
MARKET_DETAIL_VIEWED = "market_detail_viewed"
MARKET_UNINSTALLED = "market_uninstalled"
MARKET_LISTING_CHANGED = "market_listing_changed"
MARKET_SOURCE_SYNC_COMPLETED = "market_source_sync_completed"

MARKET_EVENT_NAMES = (
    MARKET_SUBSCRIBE_SUCCEEDED,
    MARKET_SUBSCRIBE_REJECTED,
    MARKET_LIST_VIEWED,
    MARKET_SEARCH_SUBMITTED,
    MARKET_DETAIL_VIEWED,
    MARKET_UNINSTALLED,
    MARKET_LISTING_CHANGED,
    MARKET_SOURCE_SYNC_COMPLETED,
)

# 字面量与 types.py 错误码对齐；本模块禁止 import power_market（R9 环）。
_REJECT_REASON = {
    "MARKET_COMING_SOON": "coming_soon",
    "MARKET_NOT_FOUND": "unlisted",
    "MARKET_HOST_INCOMPAT": "host_incompat",
    "MARKET_READONLY_ROLE": "readonly",
}


def _actor(user) -> dict[str, Any]:
    if user is None:
        return {}
    return {
        "tenant_id": getattr(user, "tenant_id", None),
        "actor_user_id": getattr(user, "id", None),
        "role": getattr(user, "tenant_role", None) or getattr(user, "role", None),
    }


async def emit_market_event(
    session: AsyncSession, event_name: str, *,
    tenant_id: int | None = None, actor_user_id: int | None = None,
    role: str | None = None, props: dict[str, Any] | None = None,
) -> None:
    logger.info(f"上报市场事件 | name={event_name} tenant={tenant_id}")
    await emit_product_event(
        session, event_name, tenant_id=tenant_id,
        actor_user_id=actor_user_id, role=role, props=props,
    )


async def run_subscribe(
    session: AsyncSession, market, *, asset_type, name, host, user, default=None,
):
    logger.info(f"market_events.run_subscribe | type={asset_type} name={name}")
    try:
        data = await market.subscribe_public(
            asset_type, name, host=host, user=user, default=default,
        )
    except Exception as exc:
        await _emit_rejected(session, user, host, exc)
        raise
    await emit_market_event(
        session, MARKET_SUBSCRIBE_SUCCEEDED,
        props={"host": data.get("host") or host}, **_actor(user),
    )
    return data


async def emit_public_list(
    session: AsyncSession, *, asset_type: Optional[str], host: Optional[str],
    category: Optional[str], q: Optional[str], total: int,
) -> None:
    logger.info(f"market_events.emit_public_list | type={asset_type} q={q}")
    filters: dict[str, Any] = {}
    if asset_type:
        filters["type"] = asset_type
    if host:
        filters["host"] = host
    if category:
        filters["category"] = category
    await emit_market_event(session, MARKET_LIST_VIEWED, props=filters or None)
    text = (q or "").strip()
    if not text:
        return
    await emit_market_event(
        session, MARKET_SEARCH_SUBMITTED,
        props={"q": text, "result_count": int(total or 0)},
    )


async def emit_public_detail(session: AsyncSession, item: dict) -> None:
    logger.info(f"market_events.emit_public_detail | name={item.get('name')}")
    await emit_market_event(
        session, MARKET_DETAIL_VIEWED,
        props={"type": item.get("asset_type"), "listing_state": item.get("listing_state")},
    )


async def _emit_rejected(session: AsyncSession, user, host, exc) -> None:
    reason = _REJECT_REASON.get(getattr(exc, "code", None) or "")
    if not reason:
        return
    props: dict[str, Any] = {"reason": reason}
    if host:
        props["host"] = host
    await emit_market_event(session, MARKET_SUBSCRIBE_REJECTED, props=props, **_actor(user))
