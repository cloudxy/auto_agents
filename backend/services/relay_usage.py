"""令牌用量观察：网关 key info + spend 回写本地缓存列。明文不出库。"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.llm_gateway import admin as gateway_admin
from backend.services.product_event_service import emit_product_event
from platform_core.logger import get_logger
from platform_core.timeutil import business_date_of, business_today, to_utc_naive, utcnow
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


def _entry_date(entry: dict) -> date:
    """spend 日志行归属的业务日（Asia/Shanghai；缺失归今天）。

    月度中转配额按上海月求和（quota_service.shanghai_year_month），日事实必须同一切日口径，
    否则上海每月 1 日 0–8 点的用量会记进上个月（审计 BUG-43）。
    """
    dt = parse_gateway_dt(entry.get("startTime") or entry.get("start_time") or entry.get("endTime"))
    if dt is None:
        return business_today()
    return business_date_of(dt)


async def observe_gateway_usage(row: RelayToken) -> tuple[int, Optional[datetime], dict[date, int]]:
    """返回 (累计 token, 最近使用时刻, 按日聚合)；按日聚合供 relay_usage_daily（审计 F3-9）"""
    logger.info(f"网关用量观察 | tenant={row.tenant_id} token={row.id}")
    info = await gateway_admin.get_key_info(str(row.key_hash))
    used = 0
    daily: dict[date, int] = {}
    page = 1
    while page <= _SPEND_LOGS_MAX_PAGES:
        logs = await gateway_admin.list_key_spend_logs(
            str(row.key_hash), page=page,
        )
        rows = (logs or {}).get("data") or []
        for entry in rows:
            tokens = int(entry.get("total_tokens") or 0)
            used += tokens
            day = _entry_date(entry)
            daily[day] = daily.get(day, 0) + tokens
        total_pages = int((logs or {}).get("total_pages") or 1)
        if page >= total_pages or not rows:
            break
        page += 1
    last_used = parse_gateway_dt(((info or {}).get("info") or {}).get("last_active"))
    return used, last_used, daily


def apply_usage(row: RelayToken, used: int, last_used: Optional[datetime]) -> bool:
    logger.debug(f"应用用量观察 | token={row.id}")
    old = int(row.used_tokens or 0)
    # 只增不减（审计 F3-9）：网关分页截断 / 日志清理不得让已记账用量倒退
    row.used_tokens = max(old, int(used))
    row.spend_synced_at = utcnow()
    if last_used is not None:
        # 网关时间可能带任意偏移；驱动写 DATETIME 时丢 tzinfo，先换算成 UTC naive
        row.last_used_at = to_utc_naive(last_used)
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
