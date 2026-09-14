"""T-19 / FR-M31：运营台待支付列表含企业名+展示金额；确认走 T-07 CAS。"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.billing import Order, Plan

CHECKOUT = "/api/v1/billing/checkout"
ADMIN_ORDERS = "/api/v1/billing/admin/orders"
CONFIRM = "/api/v1/billing/orders/{id}/confirm"
GHOST = "/api/v1/admin/tenants"


def _seed_plans(db_session) -> None:
    async def _go():
        async with db_session() as s:
            if (await s.execute(select(Plan).where(Plan.slug == "pro"))).scalar_one_or_none():
                return
            s.add_all([
                Plan(slug="pro", name="专业档", price_cents=29900, period="month", is_public=1),
                Plan(
                    slug="enterprise", name="企业档", price_cents=99900, period="month",
                    quota_json='{"task_concurrency":50,"result_storage":2000000,"llm_tokens_month":20000000}',
                    is_public=1,
                ),
            ])
            await s.commit()

    asyncio.run(_go())


def test_gwt_m31_1_list_shows_tenant_and_display_amount(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m31-1")
    pa = make_platform_admin_headers(db_session)
    created = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"})
    assert created.status_code == 201, created.text
    oid = created.json()["data"]["id"]
    listed = db_client.get(ADMIN_ORDERS, headers=pa)
    assert listed.status_code == 200, listed.text
    rows = listed.json()["data"]
    assert rows == listed.json()["data"]  # not null
    match = next(o for o in rows if o["id"] == oid)
    assert match["tenant_name"] == "公司-m31-1"
    assert match["amount_cents"] == 29900
    assert match["amount_yuan"] == 299
    assert match["status"] == "checkout_pending"


def test_gwt_m31_2_empty_list_is_array(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    listed = db_client.get(ADMIN_ORDERS, headers=pa)
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"] == []


def test_gwt_m31_3_tenant_ops_is_404(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="m31-3")
    ghost = db_client.get(GHOST, headers=owner)
    listed = db_client.get(ADMIN_ORDERS, headers=owner)
    assert listed.status_code == ghost.status_code == 404
    assert listed.json()["code"] == "HTTP_404"
    confirm = db_client.post(CONFIRM.format(id=1), headers=owner)
    assert confirm.status_code == 404


def test_gwt_m31_6_enterprise_wrong_299_rejected(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m31-6")
    pa = make_platform_admin_headers(db_session)
    created = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_enterprise"})
    oid = created.json()["data"]["id"]
    assert created.json()["data"]["amount_cents"] == 99900

    async def _tamper():
        async with db_session() as s:
            row = await s.get(Order, oid)
            row.amount_cents = 29900
            await s.commit()

    asyncio.run(_tamper())
    resp = db_client.post(CONFIRM.format(id=oid), headers=pa)
    assert resp.status_code == 422
    assert resp.json()["code"] == "CONFIRM_AMOUNT_MISMATCH"
    listed = db_client.get("/api/v1/billing/orders", headers=owner)
    assert listed.json()["data"][0]["status"] == "checkout_pending"
