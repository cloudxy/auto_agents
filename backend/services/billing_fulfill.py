"""结账履约：确认收款与通道路径共用同一写入函数（ADR-0026）。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.relay_sku_entitlement_repository import (
    RelaySkuEntitlementRepository,
)
from backend.services.quota_service import CHECKOUT_PRODUCTS, PRO_TIER_QUOTA
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.models.billing import Plan, TenantSubscription
from platform_core.models.tenant import Tenant

logger = get_logger("service.billing_fulfill")

_PERIOD_DAYS = {"month": 30, "year": 365}
_SKU_DAYS = 30


def _naive(value):
    """统一成无时区 UTC（库列 DateTime(timezone=True) 在 MySQL 读回为 naive）"""
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is not None:
        from datetime import timezone as _tz

        return value.astimezone(_tz.utc).replace(tzinfo=None)
    return value


def _quota_dict(raw) -> Optional[dict]:
    if isinstance(raw, dict):
        return dict(raw)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


async def apply_plan_quota(
    session: AsyncSession,
    tenant_id: int | None,
    plan: Plan,
    now: datetime,
    *,
    quota_override: Optional[dict] = None,
    period_days: int | None = None,
) -> None:
    """把套餐配额写入 tenants.quota + 订阅行。quota_override 优先于价目 JSON。

    审计 BUG-26（与 D22 选项无关的部分）：
    - 配额按键合并：只覆盖套餐定义的键，租户上的其它设置（交付 webhook、保留天数等）不被抹掉；
    - 账期按套餐周期计（year=365 天）：原先默认 period_days=0 → 一律 30 天，年付只给一个月；
    - 同档提前续费从当前账期末顺延，不丢剩余天数；
    - 换档（决策 D22）：立即生效，旧档剩余天数按日价折算进新档账期。
    """
    logger.info(f"履约写配额 | tenant={tenant_id} plan={getattr(plan, 'slug', None)}")
    if tenant_id is None:
        raise NotFoundException("租户")
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundException("租户")
    blob = quota_override if quota_override is not None else _quota_dict(plan.quota_json)
    if blob:
        merged = dict(tenant.quota or {}) if isinstance(tenant.quota, dict) else {}
        merged.update(blob)
        tenant.quota = merged
    days = period_days if period_days else _PERIOD_DAYS.get(plan.period, 30)
    sub = (await session.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if plan.price_cents == 0:
        tenant.expires_at = None
        end = None
    else:
        start = _naive(now)
        current_end = _naive(getattr(sub, "current_period_end", None)) if sub is not None else None
        credit = timedelta(0)
        if sub is not None and sub.status == "active" and current_end is not None and current_end > start:
            if sub.plan_id == plan.id:
                start = current_end  # 同档续费：从原到期日顺延
            else:
                # 决策 D22：换档立即生效，旧档剩余天数按日价折算成新档天数（不丢钱）
                credit = await _conversion_credit(session, sub.plan_id, current_end - start, plan, days)
        end = start + timedelta(days=days) + credit
        tenant.expires_at = end
    if sub is None:
        sub = TenantSubscription(tenant_id=tenant_id, plan_id=plan.id, status="active")
        session.add(sub)
    sub.plan_id = plan.id
    sub.status = "active"
    sub.current_period_end = end


async def _conversion_credit(
    session: AsyncSession, old_plan_id: int, remaining: timedelta, new_plan: Plan, new_days: int,
) -> timedelta:
    """旧档剩余时长按「旧日价 / 新日价」折成新档时长"""
    old = await session.get(Plan, old_plan_id)
    if old is None or not old.price_cents or not new_plan.price_cents or new_days <= 0:
        return timedelta(0)
    old_daily = float(old.price_cents) / _PERIOD_DAYS.get(old.period, 30)
    new_daily = float(new_plan.price_cents) / new_days
    credit = remaining * (old_daily / new_daily)
    logger.info(f"换档折算 | from={old.slug} to={new_plan.slug} remaining={remaining} credit={credit}")
    return credit


async def activate_relay_sku(session: AsyncSession, tenant_id: int, now: datetime, *, days: int = _SKU_DAYS) -> None:
    """开通 / 续费中转 SKU：未到期续费从当前账期末顺延（不丢剩余天数）；随后对齐网关封禁（到期被封的令牌解封）"""
    logger.info(f"开通中转 SKU | tenant={tenant_id}")
    naive = _naive(now)
    repo = RelaySkuEntitlementRepository(session)
    current = await repo.get_by_tenant_id(tenant_id)
    start = naive
    current_end = _naive(getattr(current, "period_end", None)) if current is not None else None
    if current is not None and str(current.status) == "active" and current_end and current_end > naive:
        start = current_end
    end = start + timedelta(days=days)
    await repo.activate_for_tenant(tenant_id, period_end=end, activated_at=naive)
    try:
        from backend.services.relay_enforcement import reconcile_tenant

        await reconcile_tenant(session, tenant_id, strict=False)
    except Exception as exc:  # noqa: BLE001 网关对齐失败不影响开通落库，巡检会重试
        logger.warning(f"续费后网关解封对齐失败（巡检重试） | tenant={tenant_id} err={exc}")


async def _plan_for(session: AsyncSession, order) -> Optional[Plan]:
    logger.info(f"解析履约套餐 | order={getattr(order, 'id', None)}")
    if getattr(order, "plan_id", None) is not None:
        plan = await session.get(Plan, order.plan_id)
        if plan is not None:
            return plan
    slug = {"plan_pro": "pro", "plan_enterprise": "enterprise"}.get(
        str(getattr(order, "product_code", None) or ""),
    )
    if not slug:
        return None
    return (await session.execute(select(Plan).where(Plan.slug == slug))).scalar_one_or_none()


def _enterprise_quota(plan: Plan) -> dict:
    blob = _quota_dict(plan.quota_json) or {}
    if blob and blob != PRO_TIER_QUOTA:
        return blob
    return {
        "task_concurrency": 50,
        "result_storage": 2000000,
        "llm_tokens_month": 20000000,
    }


async def fulfill_checkout_product(session: AsyncSession, order, now: datetime, *, periods: int = 1) -> None:
    """按商品码写副作用。plan_pro 永不写 SKU；enterprise/relay 写 SKU=active。

    periods：开通几个账期（自助结账恒为 1；平台为定制客户开通时按合同期数，决策 D17）。
    """
    logger.info(f"按商品开通 | order={getattr(order, 'id', None)}")
    product = str(getattr(order, "product_code", None) or "")
    tid = int(order.tenant_id)
    periods = max(1, int(periods or 1))
    if product == "relay":
        await activate_relay_sku(session, tid, now, days=_SKU_DAYS * periods)
        return
    if product not in CHECKOUT_PRODUCTS:
        return
    plan = await _plan_for(session, order)
    if plan is None:
        # 审计 BUG-25：原先静默 return，订单照样被标记已开通；改为抛错，订单停在
        # 「已付款待开通」，超管列表可见并可补偿
        logger.error(f"履约缺套餐 | order={order.id} product={product}")
        raise BusinessException(
            message="套餐已下架或不存在，无法开通", code="FULFILLMENT_PLAN_MISSING", status_code=409,
        )
    if product == "plan_pro":
        # 审计 BUG-26：不再回写价目表（履约是读价目，不是改价目）
        await apply_plan_quota(session, tid, plan, now, quota_override=PRO_TIER_QUOTA,
                               period_days=_PERIOD_DAYS.get(plan.period, 30) * periods)
        return
    if product == "plan_enterprise":
        await apply_plan_quota(session, tid, plan, now, quota_override=_enterprise_quota(plan),
                               period_days=_PERIOD_DAYS.get(plan.period, 30) * periods)
        await activate_relay_sku(session, tid, now, days=_SKU_DAYS * periods)
