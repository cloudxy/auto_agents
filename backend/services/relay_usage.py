"""令牌用量观察：网关 key info + spend 回写本地缓存列。明文不出库。"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.llm_gateway import admin as gateway_admin
from backend.services.product_event_service import emit_product_event
from platform_core.logger import get_logger
from platform_core.models.relay import RelayToken

logger = get_logger("service.relay_usage")

_SPEND_LOGS_MAX_PAGES = 10


def parse_gateway_dt(raw: object) -> Optional[datetime]:
    logger.debug("解析网关时间字段")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        logger.warning(f"网关时间字段不可解析 | raw={raw[:32]}")
        return None


async def observe_gateway_usage(row: RelayToken) -> tuple[int, Optional[datetime]]:
    logger.info(f"网关用量观察 | tenant={row.tenant_id} token={row.id}")
    info = await gateway_admin.get_key_info(str(row.key_hash))
    used = 0
    page = 1
    while page <= _SPEND_LOGS_MAX_PAGES:
        logs = await gateway_admin.list_key_spend_logs(
            str(row.key_hash), page=page,
        )
        rows = (logs or {}).get("data") or []
        for entry in rows:
            used += int(entry.get("total_tokens") or 0)
        total_pages = int((logs or {}).get("total_pages") or 1)
        if page >= total_pages or not rows:
            break
        page += 1
    last_used = parse_gateway_dt(((info or {}).get("info") or {}).get("last_active"))
    return used, last_used


def apply_usage(row: RelayToken, used: int, last_used: Optional[datetime]) -> bool:
    logger.debug(f"应用用量观察 | token={row.id}")
    old = int(row.used_tokens or 0)
    row.used_tokens = max(0, int(used))
    row.spend_synced_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if last_used is not None:
        row.last_used_at = last_used
    logger.info(
        f"回写令牌用量缓存 | tenant={row.tenant_id} token={row.id} used={row.used_tokens}"
    )
    return old == 0 and row.used_tokens >= 1


def usage_snapshot(row: RelayToken) -> dict[str, int]:
    logger.debug(f"用量事件快照 | token={row.id}")
    return {
        "token_id": int(row.id),
        "tenant_id": int(row.tenant_id),
        "group_id": int(row.group_id),
        "used_tokens": int(row.used_tokens or 0),
    }


async def emit_usage_event(session: AsyncSession, snap: dict[str, int]) -> None:
    logger.info(
        f"上报令牌用量事件 | tenant={snap['tenant_id']} token={snap['token_id']}"
    )
    await emit_product_event(
        session,
        "relay_token_call_succeeded",
        tenant_id=snap["tenant_id"],
        props={
            "token_id": snap["token_id"],
            "group_id": snap["group_id"],
            "used_tokens": snap["used_tokens"],
        },
    )


__all__ = [
    "apply_usage",
    "emit_usage_event",
    "observe_gateway_usage",
    "parse_gateway_dt",
    "usage_snapshot",
]
