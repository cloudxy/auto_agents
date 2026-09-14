"""T-10 / FR-M14：checkout_story_started + order_status_reached；第二套故事事件=0。"""
from __future__ import annotations

from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.billing import Plan
from sqlalchemy import select
import asyncio

CHECKOUT = "/api/v1/billing/checkout"
ORDERS = "/api/v1/billing/orders"
EVENTS = "/api/v1/product-events"
CONFIRM = "/api/v1/billing/orders/{id}/confirm"


def _seed(db_session) -> None:
    async def _go():
        async with db_session() as s:
            if (await s.execute(select(Plan).where(Plan.slug == "pro"))).scalar_one_or_none():
                return
            s.add(Plan(slug="pro", name="专业档", price_cents=29900, period="month", is_public=1))
            await s.commit()

    asyncio.run(_go())


def _items(db_client, pa, name: str, tid: int) -> list:
    resp = db_client.get(EVENTS, headers=pa, params={"event_name": name, "tenant_id": tid})
    assert resp.status_code == 200, resp.text
    return [r for r in resp.json()["data"]["items"] if r["event_name"] == name]


def test_gwt_m14_1_checkout_started_and_pending_reached(db_client, db_session):
    _seed(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m14-1")
    pa = make_platform_admin_headers(db_session)
    opened = db_client.get(
        f"{CHECKOUT}?product=plan_pro&referrer_surface=pricing", headers=owner,
    )
    assert opened.status_code == 200, opened.text
    created = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"})
    assert created.status_code == 201, created.text
    started = _items(db_client, pa, "checkout_story_started", tid)
    assert started
    props = started[0]["props"] or {}
    assert started[0]["tenant_id"] == tid
    assert props.get("product") == "plan_pro"
    assert props.get("surface") == "checkout"
    assert props.get("referrer_surface") == "pricing"
    assert props.get("surface") not in ("pricing", "usage")
    reached = _items(db_client, pa, "order_status_reached", tid)
    assert any((r.get("props") or {}).get("status") == "pending" for r in reached)
    assert not any((r.get("props") or {}).get("status") in ("unpaid", "fulfilling") for r in reached)


def test_gwt_m14_2_fulfilled_reached_no_second_story(db_client, db_session):
    _seed(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m14-2")
    pa = make_platform_admin_headers(db_session)
    oid = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"}).json()["data"]["id"]
    db_client.post(CONFIRM.format(id=oid), headers=pa)
    reached = _items(db_client, pa, "order_status_reached", tid)
    assert any((r.get("props") or {}).get("status") == "fulfilled" for r in reached)
    assert not any((r.get("props") or {}).get("status") in ("unpaid", "fulfilling") for r in reached)
    seconds = _items(db_client, pa, "second_checkout_story_submitted", tid)
    assert seconds == []


def test_gwt_m14_3_legacy_post_does_not_count_second_story(db_client, db_session):
    _seed(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m14-3")
    pa = make_platform_admin_headers(db_session)
    db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"})
    plans = db_client.get("/api/v1/billing/plans").json()["data"]
    pro_id = next(p["id"] for p in plans if p["slug"] == "pro")
    db_client.post(ORDERS, headers=owner, json={"plan_id": pro_id, "channel": "offline"})
    seconds = _items(db_client, pa, "second_checkout_story_submitted", tid)
    assert seconds == []


def test_gwt_m14_5_usage_referrer(db_client, db_session):
    _seed(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m14-5")
    pa = make_platform_admin_headers(db_session)
    resp = db_client.get(
        f"{CHECKOUT}?product=plan_pro&referrer_surface=usage", headers=owner,
    )
    assert resp.status_code == 200
    started = _items(db_client, pa, "checkout_story_started", tid)
    assert started
    props = started[0]["props"] or {}
    assert props.get("surface") == "checkout"
    assert props.get("referrer_surface") == "usage"
