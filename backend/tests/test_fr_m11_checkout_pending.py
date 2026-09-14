"""T-06 / FR-M11：未配通道可提交待支付；一商品一待支付；买方角色。"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from conftest import make_tenant_owner_headers
from platform_core.models.billing import Order, Plan
from platform_core.models.user import User

CHECKOUT = "/api/v1/billing/checkout"
PENDING_COPY = "已有待支付"
UNCONFIG_COPY = "收款通道未开通，提交后等待平台确认开通"
CONTACT = "请联系本企业管理员开通"
BANNED_OLD = "已有未完成的支付"
BANNED_BUY = "当前可买"


def _seed_plans(db_session) -> None:
    async def _go():
        async with db_session() as s:
            if (await s.execute(select(Plan).where(Plan.slug == "pro"))).scalar_one_or_none():
                return
            s.add_all([
                Plan(slug="free", name="免费档", price_cents=0, period="month", is_public=1),
                Plan(slug="pro", name="专业档", price_cents=29900, period="month", is_public=1),
                Plan(
                    slug="enterprise", name="企业档", price_cents=99900, period="month",
                    quota_json='{"task_concurrency":50,"result_storage":2000000,"llm_tokens_month":20000000}',
                    is_public=1,
                ),
            ])
            await s.commit()

    asyncio.run(_go())


def _member(db_session, tid: int, role: str, username: str) -> dict:
    from backend.services.auth_service import AuthService

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


def _orders(db_session, tid: int) -> list[dict]:
    async def _go():
        async with db_session() as s:
            rows = (await s.execute(
                select(Order).where(Order.tenant_id == tid).order_by(Order.id.asc())
            )).scalars().all()
            return [
                {
                    "id": int(r.id), "status": r.status, "channel": r.channel,
                    "product": r.product_code, "amount": int(r.amount_cents),
                }
                for r in rows
            ]

    return asyncio.run(_go())


def test_gwt_m11_1_unconfigured_creates_pending(db_client, db_session):
    """GWT-M11.1：两通道未配提交专业档 → 待支付 + 未配通道句。"""
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m11-1")
    resp = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert UNCONFIG_COPY in body["message"]
    data = body["data"]
    assert data["status"] == "checkout_pending"
    assert data["product_code"] == "plan_pro"
    assert data["amount_cents"] == 29900
    assert data["channel"] in (None, "")
    rows = _orders(db_session, tid)
    assert len(rows) == 1
    assert rows[0]["channel"] is None
    assert rows[0]["status"] == "checkout_pending"
    assert BANNED_BUY not in str(body)
    assert BANNED_OLD not in str(body)
    preview = db_client.get(f"{CHECKOUT}?product=plan_pro", headers=owner)
    assert preview.status_code == 200, preview.text
    pdata = preview.json()["data"]
    assert pdata["can_pay"] is False
    assert pdata.get("empty_state") == UNCONFIG_COPY
    assert pdata.get("notice") == UNCONFIG_COPY
    assert UNCONFIG_COPY in preview.json()["message"]
    assert "支付已到账，开通处理中" not in preview.text
    assert "支付未完成，套餐未开通" not in preview.text


def test_gwt_m11_2_open_checkout_shows_product_no_server_error(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m11-2")
    resp = db_client.get(f"{CHECKOUT}?product=plan_pro", headers=owner)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["product"] == "plan_pro"
    assert data["amount_cents"] == 29900
    assert data.get("empty_state") in (None, "")
    assert data.get("notice") in (None, "")
    assert UNCONFIG_COPY not in resp.text
    assert _orders(db_session, tid) == []


def test_gwt_m11_3_operator_cannot_create_pending(db_client, db_session):
    _seed_plans(db_session)
    _owner, tid = make_tenant_owner_headers(db_session, slug="m11-3")
    op = _member(db_session, tid, "operator", "m11-3-op")
    resp = db_client.post(CHECKOUT, headers=op, json={"product": "plan_pro"})
    assert CONTACT in resp.json()["message"]
    assert resp.json()["code"] == "ORDER_ROLE_NOT_ALLOWED"
    assert _orders(db_session, tid) == []


def test_gwt_m11_8_second_submit_already_pending(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m11-8")
    first = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"})
    assert first.status_code == 201, first.text
    again = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"})
    assert again.status_code == 409, again.text
    assert PENDING_COPY in again.json()["message"]
    assert BANNED_OLD not in again.json()["message"]
    assert len(_orders(db_session, tid)) == 1


def test_gwt_m11_12_concurrent_same_product_one_pending(db_client, db_session):
    """GWT-M11.12：两买方同时提交同一商品 → 至多 1 笔待支付。SQLite 生成列 UNIQUE 弱于 MySQL。"""
    _seed_plans(db_session)
    a, tid = make_tenant_owner_headers(db_session, slug="m11-12")
    b = _member(db_session, tid, "admin", "m11-12b")

    def _post(headers):
        return db_client.post(CHECKOUT, headers=headers, json={"product": "plan_pro"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        resps = [f.result() for f in (pool.submit(_post, a), pool.submit(_post, b))]
    pending = [o for o in _orders(db_session, tid) if o["status"] == "checkout_pending"]
    assert len(pending) <= 1, pending
    codes = {r.status_code for r in resps}
    assert 201 in codes
    for resp in resps:
        if resp.status_code == 409:
            assert PENDING_COPY in resp.json()["message"]
            assert resp.json()["code"] == "ORDER_PENDING_EXISTS"
        assert BANNED_OLD not in resp.text
        assert "未完成" not in resp.text


def test_gwt_m11_13_http_cancel_rejected_stays_pending(db_client, db_session):
    """GWT-M11.13：直打取消/unpaid → 404/405/422；单据仍待支付；无「未完成」。"""
    from backend.tests.payment_notify_support import tenant_quota

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m11-13")
    created = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"})
    oid = created.json()["data"]["id"]
    before = tenant_quota(db_session, tid)
    attempts = (
        ("POST", f"/api/v1/billing/orders/{oid}/cancel", None),
        ("POST", f"/api/v1/billing/checkout/{oid}/cancel", None),
        ("POST", f"/api/v1/billing/orders/{oid}/unpaid", None),
        ("PATCH", f"/api/v1/billing/orders/{oid}", {"status": "unpaid"}),
        ("DELETE", f"/api/v1/billing/orders/{oid}", None),
    )
    for method, path, body in attempts:
        resp = db_client.request(method, path, headers=owner, json=body)
        assert resp.status_code in (404, 405, 422), (method, path, resp.status_code, resp.text)
        assert "未完成" not in resp.text
    rows = _orders(db_session, tid)
    assert len(rows) == 1
    assert rows[0]["status"] == "checkout_pending"
    assert tenant_quota(db_session, tid) == before


def test_gwt_m11_14_enterprise_pending_not_299(db_client, db_session):
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m11-14")
    resp = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_enterprise"})
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["product_code"] == "plan_enterprise"
    assert data["amount_cents"] == 99900
    assert data["amount_cents"] != 29900
    assert _orders(db_session, tid)[0]["product"] == "plan_enterprise"


def test_gwt_m11_16_relay_pending(db_client, db_session, monkeypatch):
    import backend.services.billing_service as billing_mod

    orig = billing_mod.settings.get

    def _get(key, default=None):
        if key == "BILLING.RELAY_PRICE_CENTS":
            return 19900
        return orig(key, default)

    monkeypatch.setattr(billing_mod.settings, "get", _get)
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m11-16")
    resp = db_client.post(CHECKOUT, headers=owner, json={"product": "relay"})
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["product_code"] == "relay"
    assert data["amount_cents"] == 19900
    assert data["amount_cents"] != 29900
    assert _orders(db_session, tid)[0]["product"] == "relay"
