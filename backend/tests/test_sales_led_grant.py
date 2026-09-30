"""企业档走销售、平台开通（决策 D17 = A，2026-09-29「按照建议做」）

- 企业不能自助结账企业档（PLAN_SALES_LED）；价目接口标出 sales_led
- 成交后平台超管「开通套餐」：记一笔线下已收款、已开通的订单（合同金额 + 期数），
  走与自助结账同一条履约路径——订阅、企业档配额、附带的中转 SKU 按期数开通
- 只有平台超管能开通（企业负责人 404 同形）
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import select

from backend.tests.payment_notify_support import ENT_QUOTA, seed_plans, sku_status, sub_plan_slug, tenant_quota
from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.billing import Order, TenantSubscription
from platform_core.timeutil import utcnow

GRANT = "/api/v1/billing/admin/tenants/{tid}/grant"


def _orders(db_session, tid):
    async def _go():
        async with db_session() as s:
            return (await s.execute(select(Order).where(Order.tenant_id == tid))).scalars().all()

    return asyncio.run(_go())


def _period_end(db_session, tid):
    async def _go():
        async with db_session() as s:
            return (await s.execute(select(TenantSubscription.current_period_end)
                                    .where(TenantSubscription.tenant_id == tid))).scalar_one()

    return asyncio.run(_go())


def test_platform_grants_enterprise_with_contract_terms(db_client, db_session):
    seed_plans(db_session)
    _owner, tid = make_tenant_owner_headers(db_session, slug="grant-ent")
    pa = make_platform_admin_headers(db_session)
    resp = db_client.post(GRANT.format(tid=tid), headers=pa, json={
        "product": "plan_enterprise", "amount_cents": 1_200_000, "periods": 12, "note": "HT-2026-001",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "fulfilled" and data["amount_cents"] == 1_200_000
    assert data["product_code"] == "plan_enterprise" and data["channel"] == "offline"
    assert sub_plan_slug(db_session, tid) == "enterprise"
    assert tenant_quota(db_session, tid) == ENT_QUOTA
    assert sku_status(db_session, tid) == "active"
    end = _period_end(db_session, tid)
    assert abs((end - (utcnow() + timedelta(days=360))).total_seconds()) < 60
    orders = _orders(db_session, tid)
    assert len(orders) == 1 and orders[0].paid_at is not None and orders[0].fulfilled_at is not None


def test_tenant_owner_cannot_grant(db_client, db_session):
    seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="grant-self")
    resp = db_client.post(GRANT.format(tid=tid), headers=owner, json={
        "product": "plan_enterprise", "amount_cents": 0, "periods": 1,
    })
    assert resp.status_code == 404
    assert _orders(db_session, tid) == []
