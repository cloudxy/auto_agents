"""T-01（FR-50）线下订单写规则：在线零单 / 单 pending / 角色找管理员 / 无 SKU 档。

GWT-50.2 / 50.5 / 50.7 / 50.8 / 50.14 / 50.15 + §3.1 非法流转（免费档、确认后可再申请）。
对照 test_billing_relay.py（骨架四测）——本文件才是 FR-50 写规则的 Then 口径。
"""
import asyncio

from sqlalchemy import select

from platform_core.models.billing import Order, Plan
from platform_core.models.tenant import Tenant

_FORBIDDEN_CODES = {"FORBIDDEN", "QUOTA_EXCEEDED", "QUOTA_PLAN_LOCKED", "HTTP_403", "HTTP_429"}


def _seed_plans(db_session) -> None:
    """free/pro 公开；enterprise 故意 is_public=0（本波无企业档 SKU，GWT-50.14）。"""

    async def _go():
        async with db_session() as s:
            if (await s.execute(select(Plan).where(Plan.slug == "free"))).scalar_one_or_none():
                return
            s.add_all([
                Plan(slug="free", name="免费档", price_cents=0, period="month",
                     quota_json='{"task_concurrency":5,"result_storage":10000,"llm_tokens_month":200000}',
                     is_public=1),
                Plan(slug="pro", name="专业档", price_cents=29900, period="month",
                     quota_json='{"task_concurrency":20,"result_storage":500000,"llm_tokens_month":5000000}',
                     is_public=1),
                Plan(slug="enterprise", name="企业档", price_cents=99900, period="month",
                     quota_json='{"task_concurrency":50,"result_storage":2000000,"llm_tokens_month":20000000}',
                     is_public=0),
            ])
            await s.commit()

    asyncio.run(_go())


def _pro_plan_id(db_client) -> int:
    plans = db_client.get("/api/v1/billing/plans").json()["data"]
    return next(p["id"] for p in plans if p["slug"] == "pro")


def _make_member_headers(db_session, tid: int, tenant_role: str, username: str) -> dict:
    from backend.services.auth_service import AuthService
    from platform_core.models.user import User

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
                {"id": int(r.id), "status": r.status, "channel": r.channel,
                 "plan_id": r.plan_id, "key": r.idempotency_key}
                for r in rows
            ]

    return asyncio.run(_go())


def _tenant_quota(db_session, tid: int):
    async def _go():
        async with db_session() as s:
            t = (await s.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
            return t.quota

    return asyncio.run(_go())


def test_gwt_50_2_owner_offline_pro_creates_single_pending(db_client, db_session, db_engine):
    from conftest import make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t01-502")
    quota_before = _tenant_quota(db_session, tid)

    resp = db_client.post(
        "/api/v1/billing/orders", headers=owner,
        json={"plan_id": _pro_plan_id(db_client), "channel": "offline"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["status"] == "pending"
    assert "等待管理员确认收款" in resp.json()["message"]

    rows = _orders_of(db_session, tid)
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
    assert rows[0]["channel"] == "offline"
    assert rows[0]["plan_id"] == _pro_plan_id(db_client)  # 档位=pro，不是企业档
    assert rows[0]["key"] == f"pending:{tid}"  # 唯一约束业务键
    assert not [r for r in rows if r["status"] == "paid"]  # 不产生已支付在线单
    assert _tenant_quota(db_session, tid) == quota_before  # 提交不改配额


def test_gwt_50_5_online_channel_creates_no_order(db_client, db_session, db_engine):
    """PIT-2：未配通道 POST /billing/checkout 不建单（作废 alipay 经 /orders 零新行）。"""
    from conftest import make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t01-505a")

    resp = db_client.post(
        "/api/v1/billing/checkout", headers=owner,
        json={"product": "plan_pro", "channel": "alipay"},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert "收款通道未开通" in body["message"]
    assert body["code"] == "BILLING_CHANNELS_UNCONFIGURED"
    assert "PAYMENT_NOT_CONFIGURED" not in body["message"]
    assert "当前可买" not in str(body)
    assert _orders_of(db_session, tid) == []


def test_gwt_50_5_online_keeps_existing_pending(db_client, db_session, db_engine):
    from conftest import make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t01-505b")
    first = db_client.post(
        "/api/v1/billing/orders", headers=owner,
        json={"plan_id": _pro_plan_id(db_client), "channel": "offline"},
    )
    assert first.status_code == 201

    resp = db_client.post(
        "/api/v1/billing/orders", headers=owner,
        json={"plan_id": _pro_plan_id(db_client), "channel": "wechat"},
    )
    assert resp.status_code == 400
    assert "在线支付尚未开通" in resp.json()["message"]
    rows = _orders_of(db_session, tid)
    assert len(rows) == 1  # 原 pending 保持、不新开一张
    assert rows[0]["id"] == first.json()["data"]["id"]
    assert rows[0]["status"] == "pending"


def _assert_contact_admin_no_inner_code(resp) -> None:
    assert resp.status_code != 429  # 无裸 429
    body = resp.json()
    assert body["code"] not in _FORBIDDEN_CODES
    assert "请联系企业管理员" in body["message"]
    for token in ("FORBIDDEN", "QUOTA_EXCEEDED", "QUOTA_PLAN_LOCKED"):
        assert token not in body["message"]


def test_gwt_50_7_viewer_cannot_order_sees_contact_admin(db_client, db_session, db_engine):
    from conftest import make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t01-507")
    viewer = _make_member_headers(db_session, tid, "viewer", "t01-viewer")
    quota_before = _tenant_quota(db_session, tid)

    resp = db_client.post(
        "/api/v1/billing/orders", headers=viewer,
        json={"plan_id": _pro_plan_id(db_client), "channel": "offline"},
    )
    _assert_contact_admin_no_inner_code(resp)
    assert _orders_of(db_session, tid) == []  # 不产生订单
    assert _tenant_quota(db_session, tid) == quota_before  # 套餐不变


def test_gwt_50_8_operator_cannot_order_sees_contact_admin(db_client, db_session, db_engine):
    from conftest import make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t01-508")
    operator = _make_member_headers(db_session, tid, "operator", "t01-operator")

    resp = db_client.post(
        "/api/v1/billing/orders", headers=operator,
        json={"plan_id": _pro_plan_id(db_client), "channel": "offline"},
    )
    _assert_contact_admin_no_inner_code(resp)
    assert _orders_of(db_session, tid) == []


def test_gwt_50_14_enterprise_no_sku_no_order(db_client, db_session, db_engine):
    from conftest import make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t01-514")

    public = db_client.get("/api/v1/billing/plans").json()["data"]
    assert {p["slug"] for p in public} == {"free", "pro"}  # 公开价目无第三档 SKU

    async def _enterprise_id():
        async with db_session() as s:
            row = (await s.execute(select(Plan).where(Plan.slug == "enterprise"))).scalar_one()
            return int(row.id)

    ent_id = asyncio.run(_enterprise_id())
    resp = db_client.post(
        "/api/v1/billing/orders", headers=owner,
        json={"plan_id": ent_id, "channel": "offline"},
    )
    assert resp.status_code == 404
    assert _orders_of(db_session, tid) == []  # 不产生申请、不假装第三档

    ghost = db_client.post(
        "/api/v1/billing/orders", headers=owner,
        json={"plan_id": 999999, "channel": "offline"},
    )
    assert ghost.status_code == 404
    assert _orders_of(db_session, tid) == []


def test_gwt_50_15_second_pending_rejected(db_client, db_session, db_engine):
    from conftest import make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t01-515")
    quota_before = _tenant_quota(db_session, tid)
    first = db_client.post(
        "/api/v1/billing/orders", headers=owner,
        json={"plan_id": _pro_plan_id(db_client), "channel": "offline"},
    )
    assert first.status_code == 201

    resp = db_client.post(
        "/api/v1/billing/orders", headers=owner,
        json={"plan_id": _pro_plan_id(db_client), "channel": "offline"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "ORDER_PENDING_EXISTS"
    assert "已有待确认的升级申请" in body["message"]
    rows = _orders_of(db_session, tid)
    assert len(rows) == 1  # 不产生第二张
    assert rows[0]["id"] == first.json()["data"]["id"]
    assert rows[0]["status"] == "pending"  # 原单保持 pending
    assert _tenant_quota(db_session, tid) == quota_before  # 配额不变


def test_free_plan_order_rejected(db_client, db_session, db_engine):
    """§3.1 非法流转：免费档下单 → 不产生申请 + 「免费档无需下单」。"""
    from conftest import make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t01-free")

    async def _free_id():
        async with db_session() as s:
            row = (await s.execute(select(Plan).where(Plan.slug == "free"))).scalar_one()
            return int(row.id)

    resp = db_client.post(
        "/api/v1/billing/orders", headers=owner,
        json={"plan_id": asyncio.run(_free_id()), "channel": "offline"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "ORDER_FREE_PLAN"
    assert "免费档无需下单" in body["message"]
    assert _orders_of(db_session, tid) == []


def test_pending_slot_released_after_confirm(db_client, db_session, db_engine):
    """单 pending 是「同一时刻」：确认释放业务键后可再次申请（GWT-50.16 前置机制）。"""
    from conftest import make_platform_admin_headers, make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t01-rel")
    pa = make_platform_admin_headers(db_session)
    first = db_client.post(
        "/api/v1/billing/orders", headers=owner,
        json={"plan_id": _pro_plan_id(db_client), "channel": "offline"},
    )
    assert first.status_code == 201
    order_id = first.json()["data"]["id"]

    confirmed = db_client.post(f"/api/v1/billing/orders/{order_id}/confirm", headers=pa)
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["status"] == "paid"

    again = db_client.post(
        "/api/v1/billing/orders", headers=owner,
        json={"plan_id": _pro_plan_id(db_client), "channel": "offline"},
    )
    assert again.status_code == 201, again.text  # 确认后可再提交新申请
    rows = _orders_of(db_session, tid)
    assert len(rows) == 2
    assert rows[0]["status"] == "paid"
    assert rows[1]["status"] == "pending"
    assert rows[1]["key"] == f"pending:{tid}"


def test_gwt_50_verify_fail_keeps_checkout_pending(db_client, db_session, monkeypatch):
    """PIT-2：伪造成功通知（缺通道校验）保持未开通，不履约。"""
    from backend.tests.payment_notify_support import (
        checkout, install_fernet, order_row, post_notify, sub_plan_slug,
    )

    install_fernet(monkeypatch)
    fx = checkout(db_client, db_session, slug="t01-vfail")
    o = fx["order"]
    forged = {
        "order_no": o["order_no"], "merchant_no": o["merchant_id_snapshot"],
        "amount_cents": o["amount_cents"], "trade_status": "success",
    }
    resp = post_notify(db_client, "alipay", forged)
    assert resp.status_code == 200, resp.text
    assert "HMAC" not in resp.text
    assert "当前可买" not in resp.text
    row = order_row(db_session, fx["tid"])
    assert row["status"] == "checkout_pending"
    assert sub_plan_slug(db_session, fx["tid"]) is None
