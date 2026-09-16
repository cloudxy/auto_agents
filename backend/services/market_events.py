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
MARKET_LIST_PAGED = "market_list_paged"  # T-14（FR-92.5）：公开列表翻页（第 2 页起）

MARKET_EVENT_NAMES = (
    MARKET_SUBSCRIBE_SUCCEEDED,
    MARKET_SUBSCRIBE_REJECTED,
    MARKET_LIST_VIEWED,
    MARKET_SEARCH_SUBMITTED,
    MARKET_DETAIL_VIEWED,
    MARKET_UNINSTALLED,
    MARKET_LISTING_CHANGED,
    MARKET_SOURCE_SYNC_COMPLETED,
    MARKET_LIST_PAGED,
)

# ---- feat-agents-market（FR-08）治理埋点四事件 + 详情打开 ----
SYNC_COMPLETED = "sync_completed"
SYNC_FAILED = "sync_failed"
IMPORT_COMPLETED = "import_completed"
IMPORT_FAILED = "import_failed"
DETAIL_OPENED = "detail_opened"

GOVERNANCE_EVENT_NAMES = (
    SYNC_COMPLETED,
    SYNC_FAILED,
    IMPORT_COMPLETED,
    IMPORT_FAILED,
    DETAIL_OPENED,
)

# 字面量与 types.py 错误码对齐；本模块禁止 import power_market（R9 环）。
_REJECT_REASON = {
    "MARKET_COMING_SOON": "coming_soon",
    "MARKET_NOT_FOUND": "unlisted",
    "MARKET_HOST_INCOMPAT": "host_incompat",
    "MARKET_READONLY_ROLE": "readonly",
    "MARKET_CLOSED": "market_closed",
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
    anonymous_id: str | None = None, role: str | None = None,
    props: dict[str, Any] | None = None,
) -> None:
    logger.info(f"上报市场事件 | name={event_name} tenant={tenant_id}")
    await emit_product_event(
        session, event_name, tenant_id=tenant_id,
        actor_user_id=actor_user_id, anonymous_id=anonymous_id,
        role=role, props=props,
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


async def emit_market_list_paged(
    session: AsyncSession, *, page: int, result_count: int,
    anonymous_id: str | None = None,
) -> None:
    """FR-92.5：公开列表翻到第 2 页起上报。访客事件：无 tenant_id，带 anonymous_id。"""
    logger.info(
        f"market_events.emit_market_list_paged | page={page} result_count={result_count}"
    )
    await emit_market_event(
        session, MARKET_LIST_PAGED, anonymous_id=anonymous_id,
        props={"page": int(page), "result_count": int(result_count)},
    )


async def _emit_rejected(session: AsyncSession, user, host, exc) -> None:
    reason = _REJECT_REASON.get(getattr(exc, "code", None) or "")
    if not reason:
        return
    props: dict[str, Any] = {"reason": reason}
    if host:
        props["host"] = host
    await emit_market_event(session, MARKET_SUBSCRIBE_REJECTED, props=props, **_actor(user))


# ---- feat-agents-market（FR-08）治理事件投递（GWT-08.1–08.4）----


async def emit_sync_completed(
    session: AsyncSession, *, actor: str, added: int, updated: int, unchanged: int,
) -> None:
    logger.info(
        f"market_events.emit_sync_completed | actor={actor} "
        f"added={added} updated={updated} unchanged={unchanged}"
    )
    await emit_market_event(
        session, SYNC_COMPLETED,
        props={"actor": actor, "added": int(added), "updated": int(updated),
               "unchanged": int(unchanged)},
    )


async def emit_sync_failed(session: AsyncSession, *, actor: str, error_type: str) -> None:
    logger.info(f"market_events.emit_sync_failed | actor={actor} error_type={error_type}")
    await emit_market_event(
        session, SYNC_FAILED,
        props={"actor": actor, "error_type": (error_type or "")[:128]},
    )


async def emit_import_completed(
    session: AsyncSession, *, actor_role: str, source: str, files: int,
    assets_created: int, assets_updated: int, assets_skipped: int,
    actor_user_id: int | None = None, batch_id: int | None = None,
) -> None:
    logger.info(
        f"market_events.emit_import_completed | source={source} files={files} "
        f"created={assets_created} updated={assets_updated} skipped={assets_skipped}"
    )
    props: dict[str, Any] = {
        "actor_role": actor_role, "source": source, "files": int(files),
        "assets_created": int(assets_created), "assets_updated": int(assets_updated),
        "assets_skipped": int(assets_skipped),
    }
    if batch_id is not None:
        props["batch_id"] = int(batch_id)
    await emit_market_event(
        session, IMPORT_COMPLETED, actor_user_id=actor_user_id, props=props,
    )


async def emit_import_failed(
    session: AsyncSession, *, actor_role: str, error_type: str,
    actor_user_id: int | None = None,
) -> None:
    logger.info(
        f"market_events.emit_import_failed | error_type={error_type}"
    )
    await emit_market_event(
        session, IMPORT_FAILED, actor_user_id=actor_user_id,
        props={"actor_role": actor_role, "error_type": (error_type or "")[:128]},
    )


async def emit_detail_opened(
    session: AsyncSession, *, actor_role: str, asset_type: str, asset_name: str,
    actor_user_id: int | None = None, tenant_id: int | None = None,
) -> None:
    logger.info(
        f"market_events.emit_detail_opened | role={actor_role} "
        f"type={asset_type} name={asset_name}"
    )
    await emit_market_event(
        session, DETAIL_OPENED, tenant_id=tenant_id, actor_user_id=actor_user_id,
        props={"actor_role": actor_role, "asset_type": asset_type,
               "asset_name": (asset_name or "")[:128]},
    )
