"""账期生命周期巡检（决策 D22 = A，2026-09-29「按照建议做」）

原状：到期巡检（tenant_expiry_service.TenantExpiryService）从没接进启动流程，付费账期永不到期；
照原样接上又会把到期企业整体置 expired、登录被拒，连续费页都进不去。

现在：
- 到期前 BILLING.REMINDER_DAYS（默认 7 / 3 / 1）天各提醒一次负责人（邮件，决策 D25）；
  同一账期同一档只发一次（Redis 去重），错过的较早档位不补发。
- 到期后宽限 BILLING.GRACE_DAYS（默认 3）天：仍按原套餐，进入宽限时提醒一次。
- 宽限过后降为免费档：撤掉套餐配额键（按免费档默认），企业自己的设置（交付 webhook、保留天数等）
  与全部数据保留；企业照常登录、随时可续费。企业停用（disabled）与账期到期是两件事，本巡检不停用企业。
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.mail_service import send_mail
from backend.services.product_event_service import emit_product_event
from config import settings
from platform_core.logger import get_logger
from platform_core.models.billing import Plan, TenantSubscription
from platform_core.models.tenant import Tenant
from platform_core.models.user import User
from platform_core.redis_async import get_async_redis
from platform_core.timeutil import BUSINESS_TZ, utcnow

logger = get_logger("service.subscription_lifecycle")

# 套餐决定的配额维度：降档时撤掉，按免费档默认（DEFAULT_QUOTA）
PLAN_QUOTA_KEYS = ("task_concurrency", "result_storage", "llm_tokens_month")
_REMINDER_KEY = "billing:reminder:{tenant}:{end}:{tag}"
_REMINDER_TTL = 60 * 86400


def _cfg(key: str, default: Any) -> Any:
    section = settings.get("BILLING") or {}
    value = section.get(key, default) if hasattr(section, "get") else default
    return default if value is None else value


def _naive(value: Optional[datetime]) -> Optional[datetime]:
    if value is None or value.tzinfo is None:
        return value
    from datetime import timezone

    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _local_date(value: datetime) -> str:
    from datetime import timezone

    return value.replace(tzinfo=timezone.utc).astimezone(BUSINESS_TZ).strftime("%Y-%m-%d")


async def _owner_emails(session: AsyncSession, tenant_id: int) -> list[str]:
    rows = (await session.execute(
        select(User.email).where(
            User.tenant_id == tenant_id, User.tenant_role == "owner",
            User.deleted_at.is_(None), User.is_active.is_(True),
        )
    )).scalars().all()
    return [e for e in rows if e]


async def _once(tag_key: str) -> bool:
    """同一提醒只发一次；Redis 故障时本轮不发（下一轮重试），宁可晚发不重复轰炸"""
    try:
        return bool(await get_async_redis().set(tag_key, "1", nx=True, ex=_REMINDER_TTL))
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"提醒去重读写 Redis 失败，本轮跳过 | key={tag_key} err={exc}")
        return False


class SubscriptionLifecycleService:
    """账期巡检：到期提醒 → 宽限 → 降免费档（lifespan 挂载；测试直接调 run_once）"""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if "pytest" in sys.modules:
            logger.info("账期巡检测试态不启动")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="subscription-lifecycle")
        logger.info("账期巡检已启动")

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
        interval = max(300, int(_cfg("LIFECYCLE_INTERVAL_SECONDS", 3600) or 3600))
        while self._running:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 单轮失败不中断巡检
                logger.warning(f"账期巡检轮次失败: {exc}")
            await asyncio.sleep(interval)

    async def run_once(self, session: Optional[AsyncSession] = None) -> dict[str, int]:
        logger.info("账期巡检一轮")
        if session is None:
            from platform_core.db import get_manager

            async with AsyncSession(get_manager().async_engines["DEFAULT"]) as own:
                return await self._run(own)
        return await self._run(session)

    async def _run(self, session: AsyncSession) -> dict[str, int]:
        now = utcnow()
        grace = timedelta(days=int(_cfg("GRACE_DAYS", 3)))
        thresholds = sorted(int(x) for x in (_cfg("REMINDER_DAYS", [7, 3, 1]) or []))
        stats = {"reminded": 0, "grace_notice": 0, "downgraded": 0}
        rows = (await session.execute(
            select(TenantSubscription, Plan)
            .join(Plan, Plan.id == TenantSubscription.plan_id)
            .where(
                Plan.price_cents > 0,
                TenantSubscription.status == "active",
                TenantSubscription.current_period_end.isnot(None),
            )
        )).all()
        for sub, plan in rows:
            end = _naive(sub.current_period_end)
            tid = int(sub.tenant_id)
            if now >= end + grace:
                if await self._downgrade(session, sub, plan, end):
                    stats["downgraded"] += 1
            elif now >= end:
                if await self._notify(session, tid, end, "grace",
                                      f"{plan.name}已到期，{_local_date(end + grace)} 起转为免费档",
                                      f"贵企业的{plan.name}已于 {_local_date(end)} 到期，宽限期至 {_local_date(end + grace)}。"
                                      "宽限期内一切照常；到期未续费将转为免费档，数据全部保留，随时可续费恢复。"):
                    stats["grace_notice"] += 1
            else:
                days_left = (end - now).total_seconds() / 86400
                due = [t for t in thresholds if days_left <= t]
                if due:
                    t = min(due)
                    if await self._notify(session, tid, end, f"d{t}",
                                          f"{plan.name}将在 {t} 天内到期",
                                          f"贵企业的{plan.name}将于 {_local_date(end)} 到期。请在管理后台「用量看板 → 去结账」续费，"
                                          f"续费从原到期日顺延，不损失剩余天数。到期后另有 {grace.days} 天宽限期。"):
                        stats["reminded"] += 1
        return stats

    async def _notify(self, session: AsyncSession, tenant_id: int, end: datetime, tag: str,
                      subject: str, text: str) -> bool:
        key = _REMINDER_KEY.format(tenant=tenant_id, end=int(end.timestamp()), tag=tag)
        if not await _once(key):
            return False
        emails = await _owner_emails(session, tenant_id)
        for to in emails:
            await send_mail(to, subject, text)
        logger.info(f"账期提醒 | tenant={tenant_id} tag={tag} to={len(emails)}")
        return True

    async def _downgrade(self, session: AsyncSession, sub: TenantSubscription, plan: Plan, end: datetime) -> bool:
        tid = int(sub.tenant_id)
        free = (await session.execute(select(Plan).where(Plan.slug == "free"))).scalar_one_or_none()
        if free is None:
            logger.error(f"缺免费档价目，无法降档（先补种 plans） | tenant={tid}")
            return False
        tenant = await session.get(Tenant, tid)
        if tenant is not None:
            quota = dict(tenant.quota or {}) if isinstance(tenant.quota, dict) else {}
            for key in PLAN_QUOTA_KEYS:
                quota.pop(key, None)
            tenant.quota = quota
            tenant.expires_at = None
        sub.plan_id = free.id
        sub.current_period_end = None
        sub.status = "active"
        await session.commit()
        logger.warning(f"账期到期降为免费档 | tenant={tid} from={plan.slug}")
        await emit_product_event(session, "subscription_downgraded", tenant_id=tid,
                                 props={"from_plan": plan.slug, "to_plan": "free"})
        for to in await _owner_emails(session, tid):
            await send_mail(
                to, f"{plan.name}已到期，已转为免费档",
                f"贵企业的{plan.name}已于 {_local_date(end)} 到期，现已转为免费档。全部数据保留，"
                "超出免费档额度的部分可以查看和导出，新采集按免费档额度进行。续费后立即恢复。",
            )
        return True
