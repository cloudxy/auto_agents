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
from platform_core.exceptions import NotFoundException
from platform_core.logger import get_logger
from platform_core.models.billing import Plan, TenantSubscription
from platform_core.models.tenant import Tenant

logger = get_logger("service.billing_fulfill")

_PERIOD_DAYS = {"month": 30, "year": 365}
_SKU_DAYS = 30


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
    period_days: int | None = 0,
) -> None:
    """把套餐配额写入 tenants.quota + 订阅行。quota_override 优先于价目 JSON。"""
    logger.info(f"履约写配额 | tenant={tenant_id} plan={getattr(plan, 'slug', None)}")
    if tenant_id is None:
        raise NotFoundException("租户")
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundException("租户")
    blob = quota_override if quota_override is not None else _quota_dict(plan.quota_json)
    if blob:
        tenant.quota = blob
    days = period_days if period_days is not None else _PERIOD_DAYS.get(plan.period, 30)
    if plan.price_cents == 0:
        tenant.expires_at = None
        end = None
    else:
        end = now + timedelta(days=days or 30)
        tenant.expires_at = end.replace(tzinfo=None) if getattr(end, "tzinfo", None) else end
    sub = (await session.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if sub is None:
        sub = TenantSubscription(tenant_id=tenant_id, plan_id=plan.id, status="active")
        session.add(sub)
    sub.plan_id = plan.id
    sub.status = "active"
    sub.current_period_end = end


async def activate_relay_sku(session: AsyncSession, tenant_id: int, now: datetime) -> None:
    logger.info(f"开通中转 SKU | tenant={tenant_id}")
    naive = now.replace(tzinfo=None) if now.tzinfo else now
    end = naive + timedelta(days=_SKU_DAYS)
    await RelaySkuEntitlementRepository(session).activate_for_tenant(
        tenant_id, period_end=end, activated_at=naive,
    )


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


async def fulfill_checkout_product(session: AsyncSession, order, now: datetime) -> None:
    """按商品码写副作用。plan_pro 永不写 SKU；enterprise/relay 写 SKU=active。"""
    logger.info(f"按商品开通 | order={getattr(order, 'id', None)}")
    product = str(getattr(order, "product_code", None) or "")
    tid = int(order.tenant_id)
    if product == "relay":
        await activate_relay_sku(session, tid, now)
        return
    if product not in CHECKOUT_PRODUCTS:
        return
    plan = await _plan_for(session, order)
    if plan is None:
        logger.warning(f"履约缺套餐 | order={order.id} product={product}")
        return
    if product == "plan_pro":
        stale = _quota_dict(plan.quota_json)
        if stale != PRO_TIER_QUOTA:
            plan.quota_json = json.dumps(PRO_TIER_QUOTA, separators=(",", ":"))
        await apply_plan_quota(session, tid, plan, now, quota_override=PRO_TIER_QUOTA)
        return
    if product == "plan_enterprise":
        await apply_plan_quota(session, tid, plan, now, quota_override=_enterprise_quota(plan))
        await activate_relay_sku(session, tid, now)
