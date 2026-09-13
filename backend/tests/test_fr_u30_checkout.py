"""T-16 FR-U30/U32/U35/U36：结账创建、一商品一待支付、未配通道空态、角色闸。"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.billing import Order, Plan
from platform_core.models.user import User

CHECKOUT = "/api/v1/billing/checkout"
ORDERS = "/api/v1/billing/orders"
CRED = "/api/v1/admin/payment-credentials"
EVENTS = "/api/v1/product-events"
CONTACT = "请联系本企业管理员开通"
EMPTY = "收款通道未开通"
CHANNEL_OFF = "该通道未开通"
PENDING_COPY = "已有未完成的支付"
BANNED = "当前可买"


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch):
    monkeypatch.setenv("LLM_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _seed_plans(db_session) -> None:
    async def _go():
        async with db_session() as s:
            if (await s.execute(select(Plan).where(Plan.slug == "pro"))).scalar_one_or_none():
                return
            s.add_all([
                Plan(slug="free", name="免费档", price_cents=0, period="month", is_public=1),
                Plan(slug="pro", name="专业档", price_cents=29900, period="month", is_public=1),
                Plan(
                    slug="enterprise", name="企业档", price_cents=99900,
                    period="month", is_public=0,
                ),
            ])
            await s.commit()

    asyncio.run(_go())


def _member_headers(db_session, tid: int, tenant_role: str, username: str) -> dict:
    from backend.services.auth_service import AuthService

    async def _go():
        async with db_session() as s:
            s.add(User(
                username=username, email=f"{username}@x.co", password_hash="x",
                role=tenant_role, tenant_id=tid, tenant_role=tenant_role, is_active=True,
            ))
            await s.commit()
            u = (await s.execute(select(User).where(User.username == username))).scalar_one()
            token = await AuthService(s).create_token({
                "id": u.id, "username": u.username, "is_admin": False, "role": tenant_role,
                "tenant_id": tid, "tenant_role": tenant_role, "is_platform_admin": False,
            })
            return token.access_token

    return {"Authorization": f"Bearer {asyncio.run(_go())}"}


def _orders_of(db_session, tid: int) -> list[dict]:
    async def _go():
        async with db_session() as s:
            rows = (await s.execute(
                select(Order).where(Order.tenant_id == tid).order_by(Order.id.asc())
            )).scalars().all()
            return [
                {
                    "id": int(r.id), "status": r.status, "channel": r.channel,
                    "product": r.product_code, "amount": int(r.amount_cents),
                    "plan_id": r.plan_id, "fail": r.fail_reason,
                }
                for r in rows
            ]

    return asyncio.run(_go())


def _put_channel(db_client, db_session, channel: str) -> dict:
    pa = make_platform_admin_headers(db_session)
    secret = "sk-t16-" + uuid.uuid4().hex
    resp = db_client.put(CRED, headers=pa, json={
        "channel": channel, "merchant_no": f"mch-{channel}", "secrets": secret,
    })
    assert resp.status_code == 200, resp.text
    return pa


def test_gwt_u32_2_get_both_unconfigured_200_empty_no_order(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="u32-2")
    before = _orders_of(db_session, tid)
    resp = db_client.get(f"{CHECKOUT}?product=plan_pro", headers=owner)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert EMPTY in (body.get("message") or "") + str(body.get("data") or "")
    assert body["data"]["can_pay"] is False
    assert body["data"]["order_id"] is None
    assert BANNED not in str(body)
    assert _orders_of(db_session, tid) == before


def test_gwt_u32_2_post_both_unconfigured_no_order(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="u32-2p")
    resp = db_client.post(
        CHECKOUT, headers=owner, json={"product": "plan_pro", "channel": "alipay"},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["code"] == "BILLING_CHANNELS_UNCONFIGURED"
    assert EMPTY in body["message"]
    assert BANNED not in str(body)
    assert _orders_of(db_session, tid) == []


def test_one_channel_unconfigured_other_selectable(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="u32-sel")
    _put_channel(db_client, db_session, "alipay")
    resp = db_client.get(f"{CHECKOUT}?product=plan_pro", headers=owner)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    by_ch = {c["channel"]: c for c in body["data"]["channels"]}
    assert by_ch["alipay"]["selectable"] is True
    assert by_ch["wechat"]["selectable"] is False
    assert body["data"]["can_pay"] is True
    assert body["data"]["empty_state"] in (None, "")
    assert EMPTY not in (body.get("message") or "")
    assert BANNED not in str(body)
    assert _orders_of(db_session, tid) == []


def test_gwt_u30_1_alipay_creates_pending(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="u30-1")
    _put_channel(db_client, db_session, "alipay")
    resp = db_client.post(
        CHECKOUT, headers=owner, json={"product": "plan_pro", "channel": "alipay"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["status"] == "checkout_pending"
    assert data["channel"] == "alipay"
    assert data["product_code"] == "plan_pro"
    assert data["amount_cents"] == 29900
    assert "/register" not in resp.text
    assert BANNED not in resp.text
    rows = _orders_of(db_session, tid)
    assert len(rows) == 1
    assert rows[0]["channel"] == "alipay"
    assert rows[0]["status"] == "checkout_pending"


def test_gwt_u30_4_wechat_creates_pending(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="u30-4")
    _put_channel(db_client, db_session, "wechat")
    resp = db_client.post(
        CHECKOUT, headers=owner, json={"product": "plan_pro", "channel": "wechat"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["channel"] == "wechat"
    assert data["status"] == "checkout_pending"
    assert data["channel"] != "alipay"


def test_gwt_u30_2_second_pending_409(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="u30-2")
    _put_channel(db_client, db_session, "alipay")
    first = db_client.post(
        CHECKOUT, headers=owner, json={"product": "plan_pro", "channel": "alipay"},
    )
    assert first.status_code == 201, first.text
    again = db_client.post(
        CHECKOUT, headers=owner, json={"product": "plan_pro", "channel": "alipay"},
    )
    assert again.status_code == 409, again.text
    body = again.json()
    assert body["code"] == "CHECKOUT_PENDING_EXISTS"
    assert PENDING_COPY in body["message"]
    rows = _orders_of(db_session, tid)
    assert len(rows) == 1
    assert rows[0]["id"] == first.json()["data"]["id"]


def test_gwt_u30_3_tenant_a_cannot_see_b(db_client, db_session):
    _seed_plans(db_session)
    a, tid_a = make_tenant_owner_headers(db_session, slug="u30-3a")
    b, tid_b = make_tenant_owner_headers(db_session, slug="u30-3b")
    _put_channel(db_client, db_session, "alipay")
    created = db_client.post(
        CHECKOUT, headers=b, json={"product": "plan_pro", "channel": "alipay"},
    )
    assert created.status_code == 201, created.text
    listed = db_client.get(ORDERS, headers=a)
    assert listed.status_code == 200, listed.text
    ids = [row["id"] for row in listed.json()["data"]]
    assert created.json()["data"]["id"] not in ids
    assert _orders_of(db_session, tid_a) == []
    assert len(_orders_of(db_session, tid_b)) == 1


def test_gwt_u32_1_unconfigured_channel_pending_then_unpaid(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="u32-1")
    pa = _put_channel(db_client, db_session, "alipay")
    resp = db_client.post(
        CHECKOUT, headers=owner, json={"product": "plan_pro", "channel": "wechat"},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["code"] == "BILLING_CHANNEL_UNCONFIGURED"
    assert CHANNEL_OFF in body["message"]
    assert BANNED not in str(body)
    rows = _orders_of(db_session, tid)
    assert len(rows) == 1
    assert rows[0]["status"] == "unpaid"
    assert rows[0]["fail"] == "unconfigured"
    assert rows[0]["channel"] == "wechat"
    preview = db_client.get(f"{CHECKOUT}?product=plan_pro", headers=owner)
    by_ch = {c["channel"]: c for c in preview.json()["data"]["channels"]}
    assert by_ch["alipay"]["selectable"] is True
    events = db_client.get(EVENTS, headers=pa, params={"event_name": "payment_failed"})
    assert events.status_code == 200, events.text
    items = events.json()["data"]["items"]
    assert any(
        i["event_name"] == "payment_failed"
        and (i.get("props") or {}).get("reason") == "unconfigured"
        for i in items
    )
    succeeded = db_client.get(EVENTS, headers=pa, params={"event_name": "payment_succeeded"})
    assert succeeded.json()["data"]["items"] == []


def test_gwt_u35_1_product_plan_pro(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="u35-1")
    _put_channel(db_client, db_session, "alipay")
    resp = db_client.post(
        CHECKOUT, headers=owner, json={"product": "plan_pro", "channel": "alipay"},
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["product_code"] == "plan_pro"
    assert _orders_of(db_session, tid)[0]["product"] == "plan_pro"


def test_gwt_u35_5_product_plan_enterprise(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="u35-5")
    _put_channel(db_client, db_session, "alipay")
    resp = db_client.post(
        CHECKOUT, headers=owner, json={"product": "plan_enterprise", "channel": "alipay"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["product_code"] == "plan_enterprise"
    assert data["amount_cents"] == 99900
    assert _orders_of(db_session, tid)[0]["product"] == "plan_enterprise"


def test_gwt_u35_6_product_relay(db_client, db_session, monkeypatch):
    _seed_plans(db_session)
    import backend.services.billing_service as billing_mod

    orig = billing_mod.settings.get

    def _get(key, default=None):
        if key == "BILLING.RELAY_PRICE_CENTS":
            return 19900
        return orig(key, default)

    monkeypatch.setattr(billing_mod.settings, "get", _get)
    owner, tid = make_tenant_owner_headers(db_session, slug="u35-6")
    _put_channel(db_client, db_session, "alipay")
    resp = db_client.post(
        CHECKOUT, headers=owner, json={"product": "relay", "channel": "alipay"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["product_code"] == "relay"
    assert data["plan_id"] is None
    assert data["amount_cents"] == 19900
    listed = db_client.get(ORDERS, headers=owner)
    assert listed.status_code == 200, listed.text
    assert any(row["product_code"] == "relay" for row in listed.json()["data"])
    assert _orders_of(db_session, tid)[0]["plan_id"] is None


def test_gwt_u35_3_viewer_no_order(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="u35-3")
    _put_channel(db_client, db_session, "alipay")
    viewer = _member_headers(db_session, tid, "viewer", "u35-3-ro")
    resp = db_client.post(
        CHECKOUT, headers=viewer, json={"product": "plan_pro", "channel": "alipay"},
    )
    assert CONTACT in resp.json()["message"]
    assert _orders_of(db_session, tid) == []
    assert BANNED not in resp.text


def test_gwt_u36_2_operator_contact_admin_no_order(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="u36-2")
    _put_channel(db_client, db_session, "alipay")
    op = _member_headers(db_session, tid, "operator", "u36-2-op")
    resp = db_client.post(
        CHECKOUT, headers=op, json={"product": "plan_pro", "channel": "alipay"},
    )
    assert CONTACT in resp.json()["message"]
    assert _orders_of(db_session, tid) == []
    got = db_client.get(f"{CHECKOUT}?product=plan_pro", headers=op)
    assert CONTACT in got.json()["message"]
    assert _orders_of(db_session, tid) == []


def test_gwt_u36_3_anonymous_no_order(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="u36-3")
    before = _orders_of(db_session, tid)
    resp = db_client.post(CHECKOUT, json={"product": "plan_pro", "channel": "alipay"})
    assert resp.status_code in (401, 403)
    assert _orders_of(db_session, tid) == before


def test_gwt_u36_4_superadmin_cannot_pay(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="u36-4")
    pa = _put_channel(db_client, db_session, "alipay")
    resp = db_client.post(
        CHECKOUT, headers=pa, json={"product": "plan_pro", "channel": "alipay"},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["code"] == "CHECKOUT_SUPERADMIN_FORBIDDEN"
    assert "超管不能代企业支付" in resp.json()["message"]
    assert _orders_of(db_session, tid) == []


def test_checkout_rejects_unknown_product_and_channel(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="u30-bad")
    _put_channel(db_client, db_session, "alipay")
    bad_product = db_client.post(
        CHECKOUT, headers=owner, json={"product": "plan_ent", "channel": "alipay"},
    )
    assert bad_product.status_code == 422
    bad_channel = db_client.post(
        CHECKOUT, headers=owner, json={"product": "plan_pro", "channel": "paypal"},
    )
    assert bad_channel.status_code == 422
    assert _orders_of(db_session, tid) == []
