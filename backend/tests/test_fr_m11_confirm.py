"""T-07 / FR-M11：confirm 接 checkout_pending；[SEC-3] 本笔+金额；再确认不叠；迟到记 late_notify_at。"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from backend.tests.payment_notify_support import (
    checkout, install_fernet, order_row, post_notify, signed_body, sku_count,
    sku_status, sub_plan_slug, tenant_quota,
)
from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.billing import Order, Plan

CHECKOUT = "/api/v1/billing/checkout"
CONFIRM = "/api/v1/billing/orders/{id}/confirm"
PRO_QUOTA = {
    "task_concurrency": 50, "result_storage": 200000, "llm_tokens_month": 5000000,
}


def _seed_plans(db_session) -> None:
    async def _go():
        async with db_session() as s:
            if (await s.execute(select(Plan).where(Plan.slug == "pro"))).scalar_one_or_none():
                return
            s.add_all([
                Plan(
                    slug="pro", name="专业档", price_cents=29900, period="month",
                    quota_json='{"task_concurrency":20,"result_storage":500000,"llm_tokens_month":5000000}',
                    is_public=1,
                ),
                Plan(
                    slug="enterprise", name="企业档", price_cents=99900, period="month",
                    quota_json='{"task_concurrency":50,"result_storage":2000000,"llm_tokens_month":20000000}',
                    is_public=1,
                ),
            ])
            await s.commit()

    asyncio.run(_go())


def test_gwt_m11_4_confirm_checkout_pending_fulfills_pro(db_client, db_session):
    """GWT-M11.4：超管确认专业档待支付 → fulfilled；不走通道验真。"""
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m11-4")
    pa = make_platform_admin_headers(db_session)
    created = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"})
    assert created.status_code == 201, created.text
    oid = created.json()["data"]["id"]
    resp = db_client.post(CONFIRM.format(id=oid), headers=pa)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "fulfilled"
    assert "已确认" not in resp.text
    listed = db_client.get("/api/v1/billing/orders", headers=owner)
    assert listed.json()["data"][0]["status"] == "fulfilled"
    assert tenant_quota(db_session, tid)["task_concurrency"] == 50
    assert sku_status(db_session, tid) == "none"


def test_gwt_m11_5_reconfirm_noop_no_stack(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m11-5")
    pa = make_platform_admin_headers(db_session)
    oid = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"}).json()["data"]["id"]
    first = db_client.post(CONFIRM.format(id=oid), headers=pa)
    assert first.status_code == 200
    quota = dict(tenant_quota(db_session, tid))
    second = db_client.post(CONFIRM.format(id=oid), headers=pa)
    assert second.status_code == 200, second.text
    assert second.json()["data"]["status"] == "fulfilled"
    assert tenant_quota(db_session, tid) == quota
    async def _count():
        async with db_session() as s:
            return len((await s.execute(select(Order).where(Order.tenant_id == tid))).scalars().all())
    assert asyncio.run(_count()) == 1


def test_gwt_m11_6_tenant_cannot_self_fulfill(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m11-6")
    oid = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"}).json()["data"]["id"]
    resp = db_client.post(CONFIRM.format(id=oid), headers=owner)
    assert resp.status_code in (403, 404)
    assert order_row(db_session, tid)["status"] == "checkout_pending"
    q = tenant_quota(db_session, tid) or {}
    assert q.get("task_concurrency") != 50


def test_gwt_m31_4_amount_mismatch_stays_pending(db_client, db_session):
    """GWT-M31.4 / [SEC-3]：快照被改成非展示金额 → 拒绝，配额不变。"""
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m31-4")
    pa = make_platform_admin_headers(db_session)
    oid = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"}).json()["data"]["id"]

    async def _tamper():
        async with db_session() as s:
            row = await s.get(Order, oid)
            row.amount_cents = 1
            await s.commit()

    asyncio.run(_tamper())
    before = tenant_quota(db_session, tid)
    resp = db_client.post(CONFIRM.format(id=oid), headers=pa)
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "CONFIRM_AMOUNT_MISMATCH"
    assert order_row(db_session, tid)["status"] == "checkout_pending"
    assert tenant_quota(db_session, tid) == before


def test_gwt_m31_5_wrong_order_id_in_body(db_client, db_session):
    _seed_plans(db_session)
    a, tid_a = make_tenant_owner_headers(db_session, slug="m31-5a")
    b, tid_b = make_tenant_owner_headers(db_session, slug="m31-5b")
    pa = make_platform_admin_headers(db_session)
    oa = db_client.post(CHECKOUT, headers=a, json={"product": "plan_pro"}).json()["data"]["id"]
    ob = db_client.post(CHECKOUT, headers=b, json={"product": "plan_pro"}).json()["data"]["id"]
    resp = db_client.post(
        CONFIRM.format(id=oa), headers=pa, json={"order_id": ob},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "CONFIRM_ORDER_MISMATCH"
    assert order_row(db_session, tid_a)["status"] == "checkout_pending"
    assert order_row(db_session, tid_b)["status"] == "checkout_pending"


def test_gwt_m11_11_late_notify_after_confirm_sets_late_at(db_client, db_session, monkeypatch):
    """GWT-M11.11：已开通后迟到通道成功通知 → 保持已开通、记 late_notify_at、中转仍未开通。"""
    install_fernet(monkeypatch)
    fx = checkout(db_client, db_session, slug="m11-11", product="plan_pro")
    oid = fx["order"]["id"]
    pa = fx["pa"]
    confirmed = db_client.post(CONFIRM.format(id=oid), headers=pa)
    assert confirmed.status_code == 200, confirmed.text
    assert order_row(db_session, fx["tid"])["status"] == "fulfilled"
    o = fx["order"]
    body = signed_body(
        fx["secret"], "alipay", o["order_no"], o["merchant_id_snapshot"],
        int(o["amount_cents"]), "success", channel_trade_no="late-" + o["order_no"],
    )
    post_notify(db_client, "alipay", body)
    row = order_row(db_session, fx["tid"])
    assert row["status"] == "fulfilled"
    assert row["late"] is not None
    assert sku_status(db_session, fx["tid"]) == "none"
    assert sub_plan_slug(db_session, fx["tid"]) == "pro"


def _late_success(db_client, db_session, fx) -> None:
    oid = fx["order"]["id"]
    confirmed = db_client.post(CONFIRM.format(id=oid), headers=fx["pa"])
    assert confirmed.status_code == 200, confirmed.text
    o = fx["order"]
    body = signed_body(
        fx["secret"], fx["channel"], o["order_no"], o["merchant_id_snapshot"],
        int(o["amount_cents"]), "success", channel_trade_no="late-" + o["order_no"],
    )
    post_notify(db_client, fx["channel"], body)


def test_gwt_m11_18_late_notify_enterprise_no_stack(db_client, db_session, monkeypatch):
    """GWT-M11.18：企业档已开通后迟到成功通知 → late_notify_at；配额不叠；SKU 仍 active。"""
    install_fernet(monkeypatch)
    fx = checkout(db_client, db_session, slug="m11-18e", product="plan_enterprise")
    _late_success(db_client, db_session, fx)
    row = order_row(db_session, fx["tid"])
    assert row["status"] == "fulfilled"
    assert row["late"] is not None
    assert sku_status(db_session, fx["tid"]) == "active"
    assert tenant_quota(db_session, fx["tid"]) == {
        "task_concurrency": 50, "result_storage": 2000000, "llm_tokens_month": 20000000,
    }
    assert sku_count(db_session, fx["tid"]) == 1


def test_gwt_m11_18_late_notify_relay_no_resign(db_client, db_session, monkeypatch):
    """GWT-M11.18：relay 已开通后迟到成功通知 → late_notify_at；SKU active；不重签发令牌。"""
    from platform_core.models.relay import RelayToken

    install_fernet(monkeypatch)
    import backend.services.billing_service as billing_mod

    orig = billing_mod.settings.get

    def _get(key, default=None):
        if key == "BILLING.RELAY_PRICE_CENTS":
            return 19900
        return orig(key, default)

    monkeypatch.setattr(billing_mod.settings, "get", _get)
    fx = checkout(db_client, db_session, slug="m11-18r", product="relay", channel="wechat")
    quota_before = tenant_quota(db_session, fx["tid"])
    _late_success(db_client, db_session, fx)
    row = order_row(db_session, fx["tid"])
    assert row["status"] == "fulfilled"
    assert row["late"] is not None
    assert sku_status(db_session, fx["tid"]) == "active"
    assert tenant_quota(db_session, fx["tid"]) == quota_before

    async def _tokens():
        async with db_session() as s:
            return len(list((await s.execute(
                select(RelayToken).where(RelayToken.tenant_id == fx["tid"])
            )).scalars().all()))

    assert asyncio.run(_tokens()) == 0
