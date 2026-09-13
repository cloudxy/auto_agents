"""T-22 FR-U37：超管可查 payment_succeeded/payment_failed；租户 404；props 无密钥。"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.tests.payment_notify_support import (
    BANNED, CHECKOUT, EVENTS, GHOST,
    checkout, event_items, install_fernet, order_row, post_notify, put_channel,
    seed_plans, signed_body, sku_status, sub_plan_slug,
)
from conftest import make_tenant_owner_headers


@pytest.fixture(autouse=True)
def _fernet(monkeypatch):
    install_fernet(monkeypatch)


def _ok(fx, status="success"):
    o = fx["order"]
    return signed_body(
        fx["secret"], fx["channel"], o["order_no"], o["merchant_id_snapshot"],
        int(o["amount_cents"]), status, channel_trade_no="ev-" + o["order_no"],
    )


def _assert_no_secrets(body, secret: str):
    blob = str(body)
    assert secret not in blob
    assert "secrets_encrypted" not in blob
    assert BANNED not in blob
    assert "HMAC" not in blob


def test_gwt_u37_1_succeeded_queryable_with_channel_product(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u37-1", product="plan_pro")
    post_notify(db_client, "alipay", _ok(fx))
    items = event_items(db_client, fx["pa"], "payment_succeeded", fx["tid"])
    assert items, "验真通过后应可查 payment_succeeded"
    row = items[0]
    assert row["tenant_id"] == fx["tid"]
    props = row["props"] or {}
    assert props.get("channel") == "alipay"
    assert props.get("product") == "plan_pro"
    _assert_no_secrets(row, fx["secret"])


def test_gwt_u37_2_cancel_failed_no_succeeded(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u37-2")
    post_notify(db_client, "alipay", _ok(fx, "cancel"))
    failed = event_items(db_client, fx["pa"], "payment_failed", fx["tid"])
    assert any((i.get("props") or {}).get("reason") == "cancel" for i in failed)
    assert event_items(db_client, fx["pa"], "payment_succeeded", fx["tid"]) == []
    _assert_no_secrets(failed, fx["secret"])


def test_gwt_u37_3_tenant_404_same_shape(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u37-3")
    post_notify(db_client, "alipay", _ok(fx))
    faced = db_client.get(EVENTS, headers=fx["owner"])
    ghost = db_client.get(GHOST, headers=fx["owner"])
    assert faced.status_code == ghost.status_code == 404
    fb, ob = faced.json(), ghost.json()
    assert fb["code"] == ob["code"] == "HTTP_404"
    assert fb["message"] == ob["message"] == "Not Found"
    assert "FORBIDDEN" not in faced.text
    assert "抱歉您没有权限" not in faced.text
    assert "payment_succeeded" not in faced.text
    assert fx["secret"] not in faced.text


def test_gwt_u37_4_timeout_failed_event(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u37-4")
    post_notify(db_client, "alipay", _ok(fx, "timeout"))
    failed = event_items(db_client, fx["pa"], "payment_failed", fx["tid"])
    assert any((i.get("props") or {}).get("reason") == "timeout" for i in failed)
    assert event_items(db_client, fx["pa"], "payment_succeeded", fx["tid"]) == []


def test_gwt_u37_5_channel_error_failed_plan_unchanged(db_client, db_session):
    fx = checkout(db_client, db_session, slug="u37-5")
    post_notify(db_client, "alipay", _ok(fx, "channel_error"))
    failed = event_items(db_client, fx["pa"], "payment_failed", fx["tid"])
    assert any((i.get("props") or {}).get("reason") == "channel_error" for i in failed)
    assert event_items(db_client, fx["pa"], "payment_succeeded", fx["tid"]) == []
    assert sub_plan_slug(db_session, fx["tid"]) is None
    assert order_row(db_session, fx["tid"])["status"] == "unpaid"


def test_gwt_u37_6_unconfigured_failed_no_succeeded(db_client, db_session):
    seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="u37-6")
    pa, secret, _m = put_channel(db_client, db_session, "alipay")
    resp = db_client.post(
        CHECKOUT, headers=owner, json={"product": "plan_pro", "channel": "wechat"},
    )
    assert resp.status_code == 422
    failed = event_items(db_client, pa, "payment_failed", tid)
    assert any((i.get("props") or {}).get("reason") == "unconfigured" for i in failed)
    assert event_items(db_client, pa, "payment_succeeded", tid) == []
    assert order_row(db_session, tid)["status"] == "unpaid"
    _assert_no_secrets(failed, secret)


def test_gwt_u37_7_succeeded_visible_before_fulfill(db_client, db_session, monkeypatch):
    monkeypatch.setattr(
        "backend.services.payment_notify_service.PaymentNotifyService._fulfill",
        AsyncMock(return_value=None),
    )
    fx = checkout(db_client, db_session, slug="u37-7")
    post_notify(db_client, "alipay", _ok(fx))
    assert order_row(db_session, fx["tid"])["status"] == "paid_pending_fulfillment"
    items = event_items(db_client, fx["pa"], "payment_succeeded", fx["tid"])
    assert items
    props = items[0]["props"] or {}
    assert props.get("channel") == "alipay"
    assert props.get("product") == "plan_pro"
    assert items[0]["tenant_id"] == fx["tid"]
    assert sub_plan_slug(db_session, fx["tid"]) is None
    assert sku_status(db_session, fx["tid"]) == "none"
    _assert_no_secrets(items, fx["secret"])


def test_gwt_u37_8_open_checkout_no_payment_events(db_client, db_session):
    from conftest import make_platform_admin_headers

    seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="u37-8")
    headers = make_platform_admin_headers(db_session)
    before_s = event_items(db_client, headers, "payment_succeeded", tid)
    before_f = event_items(db_client, headers, "payment_failed", tid)
    resp = db_client.get(f"{CHECKOUT}?product=plan_pro", headers=owner)
    assert resp.status_code == 200
    assert "收款通道未开通" in resp.json()["message"]
    assert order_row(db_session, tid) is None
    assert event_items(db_client, headers, "payment_succeeded", tid) == before_s
    assert event_items(db_client, headers, "payment_failed", tid) == before_f
