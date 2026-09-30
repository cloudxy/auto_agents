"""中转上线闸：额度 / 停用 / 到期在网关侧执行（审计 BUG-28 / F3-9，D19 = 卖）

原先令牌额度、渠道组停用、SKU 到期都只在本地门控：已签发的 key 在网关上始终有效，
租户可以无限消耗平台 LiteLLM 成本。本模块把「令牌此刻应不应该被封」收成一个纯判定
（desired_block_reason），再由 reconcile_tokens 与网关对齐（block / unblock），做到幂等：
签发后、观察用量后、改组后、巡检时都调同一个函数，状态迁移（到期、续费、重新启用、
额度调高）自然收敛。

用量事实：网关 spend 日志按 (令牌, 业务日 Asia/Shanghai) 聚合写 relay_usage_daily，只增不减；
企业月度中转用量 = 本月事实求和，与 LLM 月度 token 分开计（D19：中转单独计配额，
租户侧只显示 token，不显示成本）。
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, timezone
from typing import Iterable, Optional

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.llm_gateway import admin as gateway_admin
from platform_core.logger import get_logger
from platform_core.models.relay import RelayGroup, RelayToken, RelayUsageDaily
from platform_core.models.relay_sku_entitlement import RelaySkuEntitlement
from platform_core.models.tenant import Tenant

logger = get_logger("service.relay_enforcement")

REASON_SKU_EXPIRED = "sku_expired"
REASON_GROUP_DISABLED = "group_disabled"
REASON_TENANT_QUOTA = "tenant_quota"
REASON_QUOTA_EXHAUSTED = "quota_exhausted"

# 默认企业月度中转额度（token）；0 或负数 = 不限。运营参数，按成本模型调整
_DEFAULT_MONTHLY_TOKENS = 10_000_000


def _relay_cfg(key: str, default=None):
    """读 RELAY 段子键（先取段再取键，避免点路径在 Dynaconf 内部带 parent 递归）"""
    from config import settings

    section = settings.get("RELAY") or {}
    value = section.get(key) if hasattr(section, "get") else None
    return default if value is None else value


def utc_now_naive() -> datetime:
    logger.debug("取 UTC 当前时刻（无时区）")
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def sku_effective_status(row: Optional[RelaySkuEntitlement], now: Optional[datetime] = None) -> str:
    """SKU 读时判到期（审计 B2-1）：active 但账期已过 ≡ expired；缺行 ≡ none"""
    logger.debug(f"判定 SKU 生效状态 | tenant={getattr(row, 'tenant_id', None)}")
    if row is None:
        return "none"
    status = str(row.status or "none")
    if status not in ("none", "active", "expired"):
        return "none"
    period_end = _naive(row.period_end)
    if status == "active" and period_end is not None and period_end < (now or utc_now_naive()):
        return "expired"
    return status


def tenant_relay_limit(tenant: Optional[Tenant]) -> int:
    """企业月度中转额度：tenants.quota.relay_tokens_month 优先，否则 RELAY.SKU_MONTHLY_TOKENS"""
    logger.debug(f"读企业月度中转额度 | tenant={getattr(tenant, 'id', None)}")
    quota = tenant.quota if tenant is not None and isinstance(tenant.quota, dict) else {}
    raw = quota.get("relay_tokens_month")
    if raw is None:
        raw = _relay_cfg("SKU_MONTHLY_TOKENS", _DEFAULT_MONTHLY_TOKENS)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_MONTHLY_TOKENS


def _month_bounds(year_month: str) -> tuple[date, date]:
    year, month = (int(x) for x in year_month.split("-"))
    start = date(year, month, 1)
    end = date(year + (month // 12), (month % 12) + 1, 1)
    return start, end


async def tenant_month_relay_used(session: AsyncSession, tenant_id: int, year_month: str) -> int:
    """企业当月中转用量（token）：relay_usage_daily 求和"""
    logger.debug(f"企业月度中转用量 | tenant={tenant_id} month={year_month}")
    start, end = _month_bounds(year_month)
    total = (await session.execute(
        select(func.coalesce(func.sum(RelayUsageDaily.total_tokens), 0)).where(
            RelayUsageDaily.tenant_id == tenant_id,
            RelayUsageDaily.stat_date >= start,
            RelayUsageDaily.stat_date < end,
        )
    )).scalar_one()
    return int(total or 0)


async def record_daily_usage(
    session: AsyncSession, row: RelayToken, daily: dict[date, int],
) -> int:
    """写日粒度事实（只增不减）；返回该令牌全部日期的累计 token"""
    logger.debug(f"写中转日用量 | token={row.id} days={len(daily)}")
    for stat_date, tokens in daily.items():
        tokens = max(0, int(tokens or 0))
        existing = (await session.execute(
            select(RelayUsageDaily).where(
                RelayUsageDaily.token_id == row.id, RelayUsageDaily.stat_date == stat_date,
            )
        )).scalar_one_or_none()
        if existing is None:
            session.add(RelayUsageDaily(
                tenant_id=row.tenant_id, token_id=row.id, stat_date=stat_date, total_tokens=tokens,
            ))
        elif tokens > int(existing.total_tokens or 0):
            existing.total_tokens = tokens
    await session.flush()
    total = (await session.execute(
        select(func.coalesce(func.sum(RelayUsageDaily.total_tokens), 0)).where(
            RelayUsageDaily.token_id == row.id)
    )).scalar_one()
    return int(total or 0)


def desired_block_reason(
    row: RelayToken, *, sku_status: str, group_status: Optional[str],
    tenant_used: int, tenant_limit: int,
) -> Optional[str]:
    """令牌此刻应被封的原因（None = 应放行）。优先级：到期 > 组停用 > 企业额度 > 令牌额度"""
    logger.debug(f"判定令牌封禁原因 | token={getattr(row, 'id', None)} sku={sku_status}")
    if sku_status != "active":
        return REASON_SKU_EXPIRED
    if group_status is not None and group_status != "enabled":
        return REASON_GROUP_DISABLED
    if tenant_limit > 0 and tenant_used >= tenant_limit:
        return REASON_TENANT_QUOTA
    quota = int(row.quota_tokens if row.quota_tokens is not None else -1)
    if quota >= 0 and int(row.used_tokens or 0) >= quota:
        return REASON_QUOTA_EXHAUSTED
    return None


class GatewayEnforcementError(Exception):
    """strict 模式下网关 block/unblock 失败（调用方据此回滚并给出可见失败）"""


async def reconcile_tokens(
    session: AsyncSession, tokens: Iterable[RelayToken], *, strict: bool = False,
) -> dict[str, int]:
    """把令牌的网关封禁状态对齐到 desired_block_reason（幂等）

    strict=True：任一网关调用失败即抛 GatewayEnforcementError（改组等用户动作，须可见失败）；
    strict=False：失败只记日志，等下一轮巡检重试（观察 / 巡检路径）。
    只处理已登记网关、未吊销的令牌；调用方负责 commit。
    """
    logger.debug(f"对齐令牌网关封禁状态 | strict={strict}")
    rows = [t for t in tokens if t.gateway_key_id and t.revoked_at is None]
    stats = {"blocked": 0, "unblocked": 0, "failed": 0}
    if not rows:
        return stats
    tenant_ids = {int(t.tenant_id) for t in rows}
    sku_rows = {
        int(r.tenant_id): r for r in (await session.execute(
            select(RelaySkuEntitlement).where(RelaySkuEntitlement.tenant_id.in_(tenant_ids))
        )).scalars().all()
    }
    groups = {
        int(g.id): g for g in (await session.execute(
            select(RelayGroup).where(RelayGroup.id.in_({int(t.group_id) for t in rows}))
        )).scalars().all()
    }
    from backend.services.quota_service import shanghai_year_month

    year_month = shanghai_year_month()
    now = utc_now_naive()
    tenant_usage: dict[int, tuple[int, int]] = {}
    for tid in tenant_ids:
        tenant = await session.get(Tenant, tid)
        tenant_usage[tid] = (
            await tenant_month_relay_used(session, tid, year_month), tenant_relay_limit(tenant),
        )
    for row in rows:
        tid = int(row.tenant_id)
        group = groups.get(int(row.group_id))
        used, limit = tenant_usage[tid]
        want = desired_block_reason(
            row, sku_status=sku_effective_status(sku_rows.get(tid), now),
            group_status=str(group.status) if group is not None else None,
            tenant_used=used, tenant_limit=limit,
        )
        have = row.blocked_reason
        if want == have:
            continue
        try:
            if want is not None and have is None:
                await gateway_admin.block_key(str(row.key_hash))
                stats["blocked"] += 1
            elif want is None and have is not None:
                await gateway_admin.unblock_key(str(row.key_hash))
                stats["unblocked"] += 1
            row.blocked_reason = want
            logger.info(f"令牌网关封禁对齐 | tenant={tid} token={row.id} {have} → {want}")
        except httpx.HTTPError as exc:
            stats["failed"] += 1
            logger.warning(
                f"网关封禁对齐失败 | tenant={tid} token={row.id} want={want} err={type(exc).__name__}"
            )
            if strict:
                raise GatewayEnforcementError(str(exc)) from exc
    await session.flush()
    return stats


async def reconcile_tenant(session: AsyncSession, tenant_id: int, *, strict: bool = False) -> dict[str, int]:
    """对齐某企业全部可用令牌"""
    logger.info(f"对齐企业令牌网关状态 | tenant={tenant_id}")
    tokens = (await session.execute(
        select(RelayToken).where(
            RelayToken.tenant_id == tenant_id, RelayToken.revoked_at.is_(None),
            RelayToken.gateway_key_id.isnot(None),
        )
    )).scalars().all()
    return await reconcile_tokens(session, tokens, strict=strict)


def _gateway_configured() -> bool:
    from backend.services.llm_gateway._settings import _base_url

    return bool(_base_url())


class RelayEnforcementService:
    """中转执法巡检：SKU 到期落库 + 全量令牌网关封禁对齐（RELAY.ENFORCE_*）"""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if "pytest" in sys.modules:
            logger.info("中转执法巡检测试态不启动")
            return
        if not bool(_relay_cfg("ENFORCE_ENABLED", True)) or not _gateway_configured():
            logger.info("中转执法巡检未启用（开关关闭或未配置 LiteLLM 网关）")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="relay-enforcement")
        logger.info("中转执法巡检已启动")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        interval = int(_relay_cfg("ENFORCE_INTERVAL_SECONDS", 600) or 600)
        while self._running:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 单轮失败不中断巡检
                logger.warning(f"中转执法巡检轮次失败: {e}")
            await asyncio.sleep(max(60, interval))

    async def run_once(self, session: Optional[AsyncSession] = None) -> dict[str, int]:
        """一轮：到期 SKU 落库 expired → 全部可用令牌对齐网关封禁状态"""
        logger.info("中转执法巡检一轮")
        if session is None:
            from platform_core.db import get_manager

            async with AsyncSession(get_manager().async_engines["DEFAULT"]) as own:
                return await self._run(own)
        return await self._run(session)

    async def _run(self, session: AsyncSession) -> dict[str, int]:
        now = utc_now_naive()
        expired = 0
        for row in (await session.execute(
            select(RelaySkuEntitlement).where(RelaySkuEntitlement.status == "active")
        )).scalars().all():
            if sku_effective_status(row, now) == "expired":
                row.status = "expired"
                expired += 1
        tokens = (await session.execute(
            select(RelayToken).where(
                RelayToken.revoked_at.is_(None), RelayToken.gateway_key_id.isnot(None),
            )
        )).scalars().all()
        stats = await reconcile_tokens(session, tokens, strict=False)
        await session.commit()
        stats["sku_expired"] = expired
        logger.info(f"中转执法巡检完成 | {stats}")
        return stats
