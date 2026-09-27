"""T-17 FR-U33/U34/U38：通知验真后履约；伪造/迟到/重复不开第二份。"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.tests.payment_notify_support import (
    BANNED, CHECKOUT, ENT_QUOTA, SKU, SUB, TOKENS,
    checkout, event_items, install_fernet, order_row, patch_relay_price,
    post_notify, put_channel, seed_plans, signed_body, sku_count, sku_status,
    sub_plan_slug, tenant_quota,
)
from conftest import make_tenant_owner_headers
from platform_core.models.user import User
from sqlalchemy import select
import asyncio

from backend.services.auth_service import AuthService


@pytest.fixture(autouse=True)
def _fernet(monkeypatch):
    install_fernet(monkeypatch)


def _member(db_session, tid: int, role: str, username: str) -> dict:
    async def _go():
        async with db_session() as s:
            s.add(User(
                username=username, email=f"{username}@x.co", password_hash="x",
                role=role, tenant_id=tid, tenant_role=role, is_active=True,
            ))
            await s.commit()
            u = (await s.execute(select(User).where(User.username == username))).scalar_one()
            token = await AuthService(s).create_token({
                "id": u.id, "username": u.username, "is_admin": False, "role": role,
                "tenant_id": tid, "tenant_role": role, "is_platform_admin": False,
            })
            return token.access_token

    return {"Authorization": f"Bearer {asyncio.run(_go())}"}


def _ok_notify(fx):
    o = fx["order"]
    return signed_body(
        fx["secret"], fx["channel"], o["order_no"], o["merchant_id_snapshot"],
        int(o["amount_cents"]), "success", channel_trade_no="tr-" + o["order_no"],
    )


def _assert_silent(resp):
    assert resp.status_code == 200, resp.text
    text = resp.text
    assert BANNED not in text
    assert "HMAC" not in text and "RSA" not in text
    assert "sha256" not in text.lower()


def test_gwt_u33_1_plan_pro_opens_pro_not_relay(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u33-1", product="plan_pro")
    quota_before = tenant_quota(db_session, fx["tid"])
    resp = post_notify(db_client, "alipay", _ok_notify(fx))
    _assert_silent(resp)
    row = order_row(db_session, fx["tid"])
    assert row["status"] == "fulfilled"
    assert sub_plan_slug(db_session, fx["tid"]) == "pro"
    assert tenant_quota(db_session, fx["tid"])["task_concurrency"] == 50
    assert tenant_quota(db_session, fx["tid"])["result_storage"] == 200000
    assert tenant_quota(db_session, fx["tid"]) != quota_before
    assert sku_status(db_session, fx["tid"]) == "none"
    sku = db_client.get(SKU, headers=fx["owner"])
    assert sku.json()["data"]["status"] == "none"
    assert "未开通中转" in sku.json()["message"]
    tokens = db_client.get(TOKENS, headers=fx["owner"])
    assert tokens.json()["data"] == []
    assert "未开通中转" in tokens.json()["message"]


def test_gwt_u33_2_no_paid_order_keeps_plan(db_client, db_session):
    seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="u33-2")
    put_channel(db_client, db_session, "alipay")
    assert order_row(db_session, tid) is None
    assert sub_plan_slug(db_session, tid) is None
    sku = db_client.get(SKU, headers=owner)
    assert sku.json()["data"]["status"] == "none"
    sub = db_client.get(SUB, headers=owner)
    assert sub.status_code == 200
    assert sub.json()["data"] is None
    assert BANNED not in sub.text


def test_gwt_u33_3_tenant_b_pay_does_not_open_a(db_client, db_session):
    a_owner, tid_a = make_tenant_owner_headers(db_session, slug="u33-3a")
    fx = checkout(db_client, db_session, slug="u33-3b", product="plan_pro")
    post_notify(db_client, "alipay", _ok_notify(fx))
    assert sub_plan_slug(db_session, fx["tid"]) == "pro"
    assert sub_plan_slug(db_session, tid_a) is None
    assert sku_status(db_session, tid_a) == "none"
    listed = db_client.get("/api/v1/billing/orders", headers=a_owner)
    ids = [r["id"] for r in listed.json()["data"]]
    assert fx["order"]["id"] not in ids


def test_gwt_u33_4_relay_wechat_opens_sku_not_plan(db_client, db_session, monkeypatch):
    patch_relay_price(monkeypatch)
    fx = checkout(
        db_client, db_session, slug="u33-4", product="relay", channel="wechat",
    )
    plan_before = sub_plan_slug(db_session, fx["tid"])
    resp = post_notify(db_client, "wechat", _ok_notify(fx))
    _assert_silent(resp)
    assert order_row(db_session, fx["tid"])["status"] == "fulfilled"
    assert sku_status(db_session, fx["tid"]) == "active"
    page = db_client.get(SKU, headers=fx["owner"])
    assert page.json()["data"]["status"] == "active"
    assert sub_plan_slug(db_session, fx["tid"]) == plan_before
    assert sku_count(db_session, fx["tid"]) == 1


def test_gwt_u33_5_verified_before_fulfill_shows_processing(db_client, db_session, monkeypatch):
    monkeypatch.setattr(
        "backend.services.payment_notify_service.PaymentNotifyService._fulfill",
        AsyncMock(return_value=None),
    )
    fx = checkout(db_client, db_session, slug="u33-5", product="plan_pro")
    post_notify(db_client, "alipay", _ok_notify(fx))
    row = order_row(db_session, fx["tid"])
    assert row["status"] == "paid_pending_fulfillment"
    assert row["verified"] is not None
    assert row["fulfilled"] is None
    preview = db_client.get(f"{CHECKOUT}?product=plan_pro", headers=fx["owner"])
    assert "支付已到账，开通处理中" not in preview.text
    assert "支付未完成，套餐未开通" not in preview.text
    assert BANNED not in preview.text
    assert sub_plan_slug(db_session, fx["tid"]) is None
    assert sku_status(db_session, fx["tid"]) == "none"


def test_gwt_u33_6_duplicate_notify_fulfills_once(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u33-6", product="plan_pro")
    body = _ok_notify(fx)
    _assert_silent(post_notify(db_client, "alipay", body))
    _assert_silent(post_notify(db_client, "alipay", body))
    rows_status = order_row(db_session, fx["tid"])["status"]
    assert rows_status == "fulfilled"
    assert sub_plan_slug(db_session, fx["tid"]) == "pro"
    assert sku_count(db_session, fx["tid"]) == 0
    assert tenant_quota(db_session, fx["tid"])["task_concurrency"] == 50


def test_gwt_u34_1_cancel_stays_unpaid(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u34-1")
    o = fx["order"]
    body = signed_body(
        fx["secret"], "alipay", o["order_no"], o["merchant_id_snapshot"],
        int(o["amount_cents"]), "cancel",
    )
    _assert_silent(post_notify(db_client, "alipay", body))
    row = order_row(db_session, fx["tid"])
    assert row["status"] == "unpaid"
    assert row["fail"] == "cancel"
    preview = db_client.get(f"{CHECKOUT}?product=plan_pro", headers=fx["owner"])
    assert "支付未完成，套餐未开通" not in preview.text
    assert "支付已到账，开通处理中" not in preview.text
    assert sub_plan_slug(db_session, fx["tid"]) is None
    assert sku_status(db_session, fx["tid"]) == "none"


def test_gwt_u34_2_timeout_not_bought(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u34-2")
    o = fx["order"]
    body = signed_body(
        fx["secret"], "alipay", o["order_no"], o["merchant_id_snapshot"],
        int(o["amount_cents"]), "timeout",
    )
    _assert_silent(post_notify(db_client, "alipay", body))
    row = order_row(db_session, fx["tid"])
    assert row["status"] == "unpaid"
    assert row["fail"] == "timeout"
    assert sub_plan_slug(db_session, fx["tid"]) is None


def test_gwt_u34_3_viewer_cannot_mark_paid(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u34-3")
    viewer = _member(db_session, fx["tid"], "viewer", "u34-3-ro")
    oid = fx["order"]["id"]
    resp = db_client.post(f"/api/v1/billing/orders/{oid}/confirm", headers=viewer)
    assert resp.status_code in (403, 404)
    assert order_row(db_session, fx["tid"])["status"] == "checkout_pending"
    assert sub_plan_slug(db_session, fx["tid"]) is None


def test_gwt_u34_4_late_success_after_cancel(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u34-4")
    o = fx["order"]
    cancel = signed_body(
        fx["secret"], "alipay", o["order_no"], o["merchant_id_snapshot"],
        int(o["amount_cents"]), "cancel",
    )
    post_notify(db_client, "alipay", cancel)
    post_notify(db_client, "alipay", _ok_notify(fx))
    row = order_row(db_session, fx["tid"])
    assert row["status"] == "unpaid"
    assert row["late"] is not None
    assert sub_plan_slug(db_session, fx["tid"]) is None
    assert sku_status(db_session, fx["tid"]) == "none"
    items = event_items(db_client, fx["pa"], "payment_succeeded", fx["tid"])
    assert items == []


def test_gwt_u34_5_channel_error_unpaid(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u34-5")
    o = fx["order"]
    body = signed_body(
        fx["secret"], "alipay", o["order_no"], o["merchant_id_snapshot"],
        int(o["amount_cents"]), "channel_error",
    )
    resp = post_notify(db_client, "alipay", body)
    _assert_silent(resp)
    row = order_row(db_session, fx["tid"])
    assert row["status"] == "unpaid"
    assert row["fail"] == "channel_error"
    assert sub_plan_slug(db_session, fx["tid"]) is None
    assert "当前可买" not in resp.text


def test_gwt_u38_2_unknown_order_no_noop(db_client, db_session):
    seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="u38-2")
    pa, secret, merchant = put_channel(db_client, db_session, "alipay")
    body = signed_body(secret, "alipay", "missing-order", merchant, 29900)
    _assert_silent(post_notify(db_client, "alipay", body))
    assert order_row(db_session, tid) is None
    assert sub_plan_slug(db_session, tid) is None
    assert event_items(db_client, pa, "payment_succeeded", tid) == []


def test_gwt_u38_3_missing_sign_stays_pending(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u38-3")
    o = fx["order"]
    forged = {
        "order_no": o["order_no"], "merchant_no": o["merchant_id_snapshot"],
        "amount_cents": o["amount_cents"], "trade_status": "success",
    }
    _assert_silent(post_notify(db_client, "alipay", forged))
    assert order_row(db_session, fx["tid"])["status"] == "checkout_pending"
    assert sub_plan_slug(db_session, fx["tid"]) is None
    assert event_items(db_client, fx["pa"], "payment_succeeded", fx["tid"]) == []


def test_gwt_u38_4_amount_mismatch(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u38-4")
    o = fx["order"]
    body = signed_body(
        fx["secret"], "alipay", o["order_no"], o["merchant_id_snapshot"], 1, "success",
    )
    _assert_silent(post_notify(db_client, "alipay", body))
    assert order_row(db_session, fx["tid"])["status"] == "checkout_pending"
    assert event_items(db_client, fx["pa"], "payment_succeeded", fx["tid"]) == []


def test_gwt_u38_5_merchant_mismatch(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u38-5")
    o = fx["order"]
    body = signed_body(
        fx["secret"], "alipay", o["order_no"], "mch-other", int(o["amount_cents"]),
    )
    _assert_silent(post_notify(db_client, "alipay", body))
    assert order_row(db_session, fx["tid"])["status"] == "checkout_pending"
    assert event_items(db_client, fx["pa"], "payment_succeeded", fx["tid"]) == []


def test_gwt_u38_6_wrong_order_no(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u38-6")
    o = fx["order"]
    body = signed_body(
        fx["secret"], "alipay", "not-" + o["order_no"], o["merchant_id_snapshot"],
        int(o["amount_cents"]),
    )
    _assert_silent(post_notify(db_client, "alipay", body))
    assert order_row(db_session, fx["tid"])["status"] == "checkout_pending"
    assert event_items(db_client, fx["pa"], "payment_succeeded", fx["tid"]) == []


def test_rotate_drops_old_secret_cannot_fulfill(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u31-5n")
    old = fx["secret"]
    new = "sk-t17-rotated-" + fx["order"]["order_no"]
    rotated = db_client.put(
        "/api/v1/admin/payment-credentials", headers=fx["pa"], json={
            "channel": "alipay",
            "merchant_no": fx["order"]["merchant_id_snapshot"],
            "secrets": new,
        },
    )
    assert rotated.status_code == 200, rotated.text
    o = fx["order"]
    stale = signed_body(
        old, "alipay", o["order_no"], o["merchant_id_snapshot"], int(o["amount_cents"]),
    )
    _assert_silent(post_notify(db_client, "alipay", stale))
    assert order_row(db_session, fx["tid"])["status"] == "checkout_pending"
    assert event_items(db_client, fx["pa"], "payment_succeeded", fx["tid"]) == []
    current = signed_body(
        new, "alipay", o["order_no"], o["merchant_id_snapshot"], int(o["amount_cents"]),
    )
    _assert_silent(post_notify(db_client, "alipay", current))
    assert order_row(db_session, fx["tid"])["status"] == "fulfilled"


def test_confirm_cannot_fulfill_online_checkout(db_client, db_session):
    """PIT-2：confirm 接结账单 → fulfilled（ADR-0026）。"""
    fx = checkout(db_client, db_session, slug="u34-cf")
    resp = db_client.post(
        f"/api/v1/billing/orders/{fx['order']['id']}/confirm", headers=fx["pa"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "fulfilled"
    assert order_row(db_session, fx["tid"])["status"] == "fulfilled"
    assert sub_plan_slug(db_session, fx["tid"]) == "pro"


def test_gwt_u35_enterprise_notify_opens_enterprise(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u33-ent", product="plan_enterprise")
    post_notify(db_client, "alipay", _ok_notify(fx))
    assert sub_plan_slug(db_session, fx["tid"]) == "enterprise"
    assert tenant_quota(db_session, fx["tid"]) == ENT_QUOTA
    assert sku_status(db_session, fx["tid"]) == "active"
