"""T-05 / FR-M10：旧 POST /billing/orders 不建第二套单。"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from conftest import make_tenant_owner_headers
from platform_core.models.billing import Order, Plan
from platform_core.models.product_event import ProductEvent

ORDERS = "/api/v1/billing/orders"
CHECKOUT = "/api/v1/billing/checkout"
STORY_COPY = "请从结账页提交开通"
BANNED_STORY = "已有未完成的支付"
BANNED_BUY = "当前可买"


def _seed_plans(db_session) -> None:
    async def _go():
        async with db_session() as s:
            if (await s.execute(select(Plan).where(Plan.slug == "pro"))).scalar_one_or_none():
                return
            s.add_all([
                Plan(slug="free", name="免费档", price_cents=0, period="month", is_public=1),
                Plan(slug="pro", name="专业档", price_cents=29900, period="month", is_public=1),
                Plan(slug="enterprise", name="企业档", price_cents=99900, period="month",
                     is_public=1),
            ])
            await s.commit()

    asyncio.run(_go())


def _pro_id(db_client) -> int:
    return next(p["id"] for p in db_client.get("/api/v1/billing/plans").json()["data"]
                if p["slug"] == "pro")


def _orders(db_session, tid: int) -> list:
    async def _go():
        async with db_session() as s:
            return list((await s.execute(
                select(Order).where(Order.tenant_id == tid)
            )).scalars().all())

    return asyncio.run(_go())


def test_gwt_m10_4_legacy_orders_post_creates_no_row(db_client, db_session):
    """GWT-M10.4：旧入口提交不产生第二套单据。"""
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m10-4")
    before = len(_orders(db_session, tid))
    resp = db_client.post(
        ORDERS, headers=owner,
        json={"plan_id": _pro_id(db_client), "channel": "offline"},
    )
    assert resp.status_code in (409, 422), resp.text
    body = resp.json()
    assert STORY_COPY in body["message"]
    assert BANNED_STORY not in body["message"]
    assert BANNED_BUY not in str(body)
    assert "second_checkout_story_submitted" not in str(body)
    assert len(_orders(db_session, tid)) == before


def test_gwt_m10_4_legacy_does_not_mutate_checkout_pending(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m10-4b")
    created = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"})
    assert created.status_code == 201, created.text
    oid = created.json()["data"]["id"]
    resp = db_client.post(
        ORDERS, headers=owner,
        json={"plan_id": _pro_id(db_client), "channel": "offline"},
    )
    assert resp.status_code in (409, 422), resp.text
    rows = _orders(db_session, tid)
    assert len(rows) == 1
    assert int(rows[0].id) == oid
    assert rows[0].status == "checkout_pending"

    async def _seconds():
        async with db_session() as s:
            return list((await s.execute(
                select(ProductEvent).where(
                    ProductEvent.event_name == "second_checkout_story_submitted",
                    ProductEvent.tenant_id == tid,
                )
            )).scalars().all())

    assert asyncio.run(_seconds()) == []
