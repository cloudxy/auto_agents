"""收费闸：订单状态机与履约（审计 BUG-24 / BUG-25 / BUG-26 / BUG-27 / R1-11 回归）

- 确认收款以下单快照为准：调价后在途订单照常确认；快照被篡改（签名不符）仍拒绝
- 买方可取消待支付；超时待支付惰性关闭，不再占坑挡死新下单
- 已付款待开通（履约失败）与迟到到账的单进入超管待处理列表，可补偿重开
- 履约：配额按键合并、不回写价目、年付 365 天、同档提前续费顺延
- prod 关闭 HMAC 夹具通知
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from backend.tests.payment_notify_support import (
    PRO_QUOTA, checkout, install_fernet, order_row, post_notify, seed_plans, signed_body,
    tenant_quota,
)
from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.billing import Order, Plan, TenantSubscription
from platform_core.models.tenant import Tenant

CHECKOUT = "/api/v1/billing/checkout"
CONFIRM = "/api/v1/billing/orders/{id}/confirm"
CANCEL = "/api/v1/billing/orders/{id}/cancel"
RETRY = "/api/v1/billing/orders/{id}/retry-fulfillment"
ADMIN_ORDERS = "/api/v1/billing/admin/orders"


def _run(coro):
    return asyncio.run(coro)


def _exec(db_session, stmt) -> None:
    async def _go():
        async with db_session() as s:
            await s.execute(stmt)
            await s.commit()
    _run(_go())


def _pro_order(db_client, db_session, slug: str) -> tuple[dict, int, int]:
    seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug=slug)
    resp = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"})
    assert resp.status_code == 201, resp.text
    return owner, tid, int(resp.json()["data"]["id"])


# ---------------- BUG-24：快照确认 ----------------


def test_confirm_after_price_change_uses_snapshot(db_client, db_session):
    owner, tid, oid = _pro_order(db_client, db_session, "bill-price")
    _exec(db_session, update(Plan).where(Plan.slug == "pro").values(price_cents=39900))
    pa = make_platform_admin_headers(db_session)
    resp = db_client.post(CONFIRM.format(id=oid), headers=pa)
    assert resp.status_code == 200, resp.text  # 原先 422 CONFIRM_AMOUNT_MISMATCH，订单卡死
    assert resp.json()["data"]["status"] == "fulfilled"
    assert resp.json()["data"]["amount_cents"] == 29900  # 按下单价


def test_order_carries_amount_signature(db_client, db_session):
    _owner, tid, _oid = _pro_order(db_client, db_session, "bill-sig")

    async def _sig():
        async with db_session() as s:
            return (await s.execute(select(Order.amount_sig).where(Order.tenant_id == tid))).scalar_one()

    assert len(_run(_sig()) or "") == 64


# ---------------- BUG-24：取消 ----------------


def test_owner_cancels_pending_then_can_reorder(db_client, db_session):
    owner, tid, oid = _pro_order(db_client, db_session, "bill-cancel")
    resp = db_client.post(CANCEL.format(id=oid), headers=owner)
    assert resp.status_code == 200, resp.text
    row = order_row(db_session, tid)
    assert (row["status"], row["fail"]) == ("unpaid", "cancel")
    again = db_client.post(CANCEL.format(id=oid), headers=owner)
    assert again.status_code == 409
    assert again.json()["code"] == "ORDER_NOT_CANCELLABLE"
    reorder = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"})
    assert reorder.status_code == 201, reorder.text  # 占坑已释放


def test_cancel_other_tenant_order_404(db_client, db_session):
    _owner, tid, oid = _pro_order(db_client, db_session, "bill-cancel-a")
    other, _ = make_tenant_owner_headers(db_session, slug="bill-cancel-b")
    assert db_client.post(CANCEL.format(id=oid), headers=other).status_code == 404
    assert order_row(db_session, tid)["status"] == "checkout_pending"


def test_cancel_fulfilled_order_409(db_client, db_session):
    owner, tid, oid = _pro_order(db_client, db_session, "bill-cancel-f")
    pa = make_platform_admin_headers(db_session)
    assert db_client.post(CONFIRM.format(id=oid), headers=pa).status_code == 200
    resp = db_client.post(CANCEL.format(id=oid), headers=owner)
    assert resp.status_code == 409
    assert order_row(db_session, tid)["status"] == "fulfilled"


# ---------------- BUG-24：超时 ----------------


def test_stale_pending_expires_and_releases_slot(db_client, db_session):
    owner, tid, oid = _pro_order(db_client, db_session, "bill-ttl")
    _exec(db_session, update(Order).where(Order.id == oid).values(
        created_at=datetime.now(timezone.utc) - timedelta(days=30)))
    reorder = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"})
    assert reorder.status_code == 201, reorder.text  # 原先 409 ORDER_PENDING_EXISTS，永远下不了单

    async def _old():
        async with db_session() as s:
            return (await s.get(Order, oid))

    old = _run(_old())
    assert (old.status, old.fail_reason) == ("unpaid", "timeout")


def test_fresh_pending_not_expired(db_client, db_session):
    owner, tid, oid = _pro_order(db_client, db_session, "bill-ttl-fresh")
    dup = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"})
    assert dup.status_code == 409
    assert order_row(db_session, tid)["status"] == "checkout_pending"


# ---------------- BUG-25：已付款待开通可见 + 补偿 ----------------


def test_fulfillment_failure_stays_visible_and_retryable(db_client, db_session, monkeypatch):
    install_fernet(monkeypatch)
    ctx = checkout(db_client, db_session, slug="bill-retry", channel="alipay")
    order = ctx["order"]
    # 套餐被下架（删价目行）→ 通道成功通知后履约失败
    _exec(db_session, update(Order).where(Order.id == order["id"]).values(plan_id=None))
    _exec(db_session, update(Plan).where(Plan.slug == "pro").values(slug="pro-gone"))
    body = signed_body(ctx["secret"], "alipay", order["order_no"], ctx["merchant"], order["amount_cents"])
    assert post_notify(db_client, "alipay", body).status_code == 200
    row = order_row(db_session, ctx["tid"])
    assert row["status"] == "paid_pending_fulfillment"  # 原先静默标记已开通

    pa = ctx["pa"]
    listed = db_client.get(ADMIN_ORDERS, headers=pa).json()["data"]
    assert order["id"] in [o["id"] for o in listed]  # 原先超管列表看不到
    failed = db_client.post(RETRY.format(id=order["id"]), headers=pa)
    assert failed.status_code == 409 and failed.json()["code"] == "FULFILLMENT_FAILED"

    _exec(db_session, update(Plan).where(Plan.slug == "pro-gone").values(slug="pro"))
    ok = db_client.post(RETRY.format(id=order["id"]), headers=pa)
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["status"] == "fulfilled"
    assert tenant_quota(db_session, ctx["tid"])["task_concurrency"] == 50


def test_retry_requires_platform_admin(db_client, db_session):
    owner, _tid, oid = _pro_order(db_client, db_session, "bill-retry-auth")
    assert db_client.post(RETRY.format(id=oid), headers=owner).status_code == 404


def test_late_paid_after_cancel_is_listed_for_admin(db_client, db_session, monkeypatch):
    install_fernet(monkeypatch)
    ctx = checkout(db_client, db_session, slug="bill-late", channel="alipay")
    order = ctx["order"]
    assert db_client.post(CANCEL.format(id=order["id"]), headers=ctx["owner"]).status_code == 200
    body = signed_body(ctx["secret"], "alipay", order["order_no"], ctx["merchant"], order["amount_cents"])
    post_notify(db_client, "alipay", body)
    row = order_row(db_session, ctx["tid"])
    assert row["status"] == "unpaid" and row["late"] is not None
    listed = db_client.get(ADMIN_ORDERS, headers=ctx["pa"]).json()["data"]
    assert order["id"] in [o["id"] for o in listed]  # 钱到了，超管必须能看到并人工处理


# ---------------- BUG-26：履约写入 ----------------


def test_fulfill_merges_quota_keeps_tenant_settings(db_client, db_session):
    owner, tid, oid = _pro_order(db_client, db_session, "bill-merge")
    _exec(db_session, update(Tenant).where(Tenant.id == tid).values(
        quota={"delivery_webhook_url": "https://hooks.example.com/x", "result_retention_days": 60}))
    pa = make_platform_admin_headers(db_session)
    assert db_client.post(CONFIRM.format(id=oid), headers=pa).status_code == 200
    q = tenant_quota(db_session, tid)
    assert q["delivery_webhook_url"] == "https://hooks.example.com/x"  # 原先整份覆盖被抹掉
    assert q["result_retention_days"] == 60
    assert q["task_concurrency"] == 50


def test_fulfill_does_not_rewrite_price_table(db_client, db_session):
    owner, tid, oid = _pro_order(db_client, db_session, "bill-nowrite")
    custom = {"task_concurrency": 7, "result_storage": 1, "llm_tokens_month": 1}
    _exec(db_session, update(Plan).where(Plan.slug == "pro").values(quota_json=json.dumps(custom)))
    pa = make_platform_admin_headers(db_session)
    assert db_client.post(CONFIRM.format(id=oid), headers=pa).status_code == 200

    async def _plan():
        async with db_session() as s:
            return (await s.execute(select(Plan.quota_json).where(Plan.slug == "pro"))).scalar_one()

    assert json.loads(_run(_plan())) == custom


def _apply(db_session, tid: int, plan_slug: str, now: datetime):
    from backend.services.billing_fulfill import apply_plan_quota

    async def _go():
        async with db_session() as s:
            plan = (await s.execute(select(Plan).where(Plan.slug == plan_slug))).scalar_one()
            await apply_plan_quota(s, tid, plan, now)
            await s.commit()
            sub = (await s.execute(
                select(TenantSubscription).where(TenantSubscription.tenant_id == tid))).scalar_one()
            end = sub.current_period_end
            return end.replace(tzinfo=None) if end.tzinfo else end

    return _run(_go())


def test_yearly_plan_gets_365_days(db_session):
    seed_plans(db_session)

    async def _mk():
        async with db_session() as s:
            t = Tenant(slug="bill-year", name="年付")
            s.add_all([t, Plan(slug="pro-year", name="专业档年付", price_cents=299000,
                               period="year", quota_json=json.dumps(PRO_QUOTA), is_public=1)])
            await s.commit()
            return int(t.id)

    tid = _run(_mk())
    now = datetime(2026, 1, 1)
    end = _apply(db_session, tid, "pro-year", now)
    assert (end - now).days == 365  # 原先 30 天


def test_early_renewal_same_plan_extends_from_period_end(db_session):
    seed_plans(db_session)

    async def _mk():
        async with db_session() as s:
            t = Tenant(slug="bill-renew", name="续费")
            s.add(t)
            await s.commit()
            return int(t.id)

    tid = _run(_mk())
    first = _apply(db_session, tid, "pro", datetime(2026, 1, 1))
    second = _apply(db_session, tid, "pro", datetime(2026, 1, 21))  # 剩 10 天时续费
    assert first == datetime(2026, 1, 31)
    assert second == datetime(2026, 3, 2)  # 1-31 起顺延 30 天，剩余天数不丢


# ---------------- BUG-27 / R1-11 ----------------


def test_superadmin_checkout_preview_403(db_client, db_session):
    seed_plans(db_session)
    pa = make_platform_admin_headers(db_session)
    resp = db_client.get(CHECKOUT, headers=pa, params={"product": "plan_pro"})
    assert resp.status_code == 403
    assert resp.json()["code"] == "CHECKOUT_SUPERADMIN_FORBIDDEN"


def test_fixture_notify_disabled_in_prod(db_client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    resp = db_client.post("/api/v1/billing/notify/alipay", json={
        "order_no": "x", "merchant_no": "m", "amount_cents": 1, "trade_status": "success", "sign": "s"})
    assert resp.status_code == 404
