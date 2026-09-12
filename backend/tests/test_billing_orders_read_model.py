"""T-02（FR-50/92）我的订单读模型 + 超管确认不可逆 + 提交/确认事件。

GWT-50.3 / 50.4（后端半：空列表）/ 50.9 / 50.10 / 50.11 / 50.16 + GWT-92.1 / 92.2。
口径：金额用户可见=元（定价页 ¥299/月 同一数字）；50.10 Then 不含配额履约（Q-PRICE）
——本文件对确认后的 quota 不做验收断言；50.16 只断言「不叠档」。
对照 test_billing_relay.py（骨架四测，不勾 FR-50 完成）。
"""
import asyncio

from sqlalchemy import select

from platform_core.models.billing import Order, Plan, TenantSubscription
from platform_core.models.product_event import ProductEvent
from platform_core.models.tenant import Tenant

PRO_QUOTA = {"task_concurrency": 20, "result_storage": 500000, "llm_tokens_month": 5000000}
ORDERS = "/api/v1/billing/orders"
EVENTS_QUERY = "/api/v1/product-events"


def _seed_plans(db_session) -> None:
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
            return [{"id": int(r.id), "status": r.status} for r in rows]

    return asyncio.run(_go())


def _tenant_state(db_session, tid: int) -> dict:
    async def _go():
        async with db_session() as s:
            t = (await s.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
            sub = (await s.execute(
                select(TenantSubscription).where(TenantSubscription.tenant_id == tid)
            )).scalar_one_or_none()
            return {
                "quota": dict(t.quota) if t.quota else None,
                "expires_at": t.expires_at,
                "period_end": sub.current_period_end if sub else None,
            }

    return asyncio.run(_go())


def _events_of(db_session, name: str, tid: int) -> list[ProductEvent]:
    async def _go():
        async with db_session() as s:
            rows = (await s.execute(
                select(ProductEvent).where(
                    ProductEvent.event_name == name, ProductEvent.tenant_id == tid,
                )
            )).scalars().all()
            return list(rows)

    return asyncio.run(_go())


def _submit_pro(db_client, owner: dict) -> dict:
    resp = db_client.post(
        ORDERS, headers=owner,
        json={"plan_id": _pro_plan_id(db_client), "channel": "offline"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def test_gwt_50_3_my_orders_show_plan_status_amount_yuan(db_client, db_session, db_engine):
    from conftest import make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t02-503")
    other, _ = make_tenant_owner_headers(db_session, slug="t02-503o")
    _submit_pro(db_client, owner)
    _submit_pro(db_client, other)

    resp = db_client.get(ORDERS, headers=owner)
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]
    assert len(items) == 1  # 看不见其他企业的单
    row = items[0]
    assert row["plan_name"] == "专业档"  # 档位名称
    assert row["status"] == "pending"  # 状态=待确认收款
    # 金额用户可见=元，与定价页该档同一数字（Pricing.tsx ¥299/月），不必心算分
    assert row["amount_yuan"] == 299
    assert row["amount_cents"] == 29900


def test_gwt_50_4_backend_half_empty_orders_returns_empty_list(db_client, db_session, db_engine):
    """空态后端半：返回空列表 200；「还没有升级申请。」句由前端承接（GWT-50.4）。"""
    from conftest import make_tenant_owner_headers

    _seed_plans(db_session)
    owner, _ = make_tenant_owner_headers(db_session, slug="t02-504")

    resp = db_client.get(ORDERS, headers=owner)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []


def test_viewer_can_read_order_list(db_client, db_session, db_engine):
    """列表是读面：只读成员也能看本企业订单（GWT-50.3 读半，与 50.7 写拒绝互不否）。"""
    from conftest import make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t02-view")
    _submit_pro(db_client, owner)
    viewer = _make_member_headers(db_session, tid, "viewer", "t02-viewer")

    resp = db_client.get(ORDERS, headers=viewer)
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]
    assert len(items) == 1
    assert items[0]["plan_name"] == "专业档"
    assert items[0]["status"] == "pending"


def test_gwt_50_9_tenant_confirm_rejected_stays_pending(db_client, db_session, db_engine):
    from conftest import make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t02-509")
    order = _submit_pro(db_client, owner)
    quota_before = _tenant_state(db_session, tid)["quota"]
    viewer = _make_member_headers(db_session, tid, "viewer", "t02-509v")

    for headers in (owner, viewer):
        resp = db_client.post(f"{ORDERS}/{order['id']}/confirm", headers=headers)
        assert resp.status_code == 403  # 仅 require_platform_admin（SEC-5）
    rows = _orders_of(db_session, tid)
    assert rows == [{"id": order["id"], "status": "pending"}]  # 申请仍待确认
    state = _tenant_state(db_session, tid)
    assert state["quota"] == quota_before  # 配额不变
    assert _events_of(db_session, "offline_order_confirmed", tid) == []  # 无确认事件


def test_gwt_50_10_admin_confirm_tenant_reads_paid(db_client, db_session, db_engine):
    """完成线=租户能读到已确认（QA-24/PC-3）；Then 不含配额履约——不断言 quota。"""
    from conftest import make_platform_admin_headers, make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t02-510")
    pa = make_platform_admin_headers(db_session)
    order = _submit_pro(db_client, owner)

    pending = db_client.get("/api/v1/billing/admin/orders", headers=pa)
    assert pending.status_code == 200, pending.text
    match = next(o for o in pending.json()["data"] if o["id"] == order["id"])
    assert match["tenant_name"] == "公司-t02-510"  # 运营台可见企业名
    assert match["amount_yuan"] == 299  # 与定价页同一金额（元）
    assert match["plan_name"] == "专业档"

    confirmed = db_client.post(f"{ORDERS}/{order['id']}/confirm", headers=pa)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["data"]["status"] == "paid"
    assert confirmed.json()["data"]["paid_at"] is not None

    # 不可逆：无任何回退入口；租户下次打开「我的订单」看到已确认
    mine = db_client.get(ORDERS, headers=owner)
    assert mine.status_code == 200
    items = mine.json()["data"]
    assert len(items) == 1
    assert items[0]["status"] == "paid"
    assert items[0]["plan_name"] == "专业档"


def test_gwt_50_11_reconfirm_no_new_row_no_stacked_side_effect(db_client, db_session, db_engine):
    from conftest import make_platform_admin_headers, make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t02-511")
    pa = make_platform_admin_headers(db_session)
    order = _submit_pro(db_client, owner)
    oid = order["id"]

    first = db_client.post(f"{ORDERS}/{oid}/confirm", headers=pa)
    assert first.status_code == 200
    snapshot = _tenant_state(db_session, tid)  # 首次确认后的配额/账期快照

    again = db_client.post(f"{ORDERS}/{oid}/confirm", headers=pa)
    assert again.status_code == 200
    assert again.json()["data"]["status"] == "paid"  # 保持已确认

    rows = _orders_of(db_session, tid)
    assert rows == [{"id": oid, "status": "paid"}]  # 不产生第二张单
    after = _tenant_state(db_session, tid)
    assert after["quota"] == snapshot["quota"]  # 不叠配额副作用
    assert after["expires_at"] == snapshot["expires_at"]  # 账期不再顺延
    assert after["period_end"] == snapshot["period_end"]
    assert len(_events_of(db_session, "offline_order_confirmed", tid)) == 1  # 不重复上报


def test_gwt_50_16_two_fixture_pendings_both_paid_no_quota_stack(
    db_client, db_session, db_engine,
):
    """夹具两张 pending（非正常入口）都确认 → 两张 paid；配额不叠档（只验收这一点）。"""
    from conftest import make_platform_admin_headers, make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t02-516")
    pa = make_platform_admin_headers(db_session)
    first = _submit_pro(db_client, owner)
    pro_id = _pro_plan_id(db_client)

    async def _insert_second_pending():
        async with db_session() as s:
            s.add(Order(
                tenant_id=tid, plan_id=pro_id, amount_cents=29900,
                status="pending", channel="offline", idempotency_key=None,
            ))
            await s.commit()

    asyncio.run(_insert_second_pending())
    rows = _orders_of(db_session, tid)
    assert len(rows) == 2 and all(r["status"] == "pending" for r in rows)

    for r in rows:
        resp = db_client.post(f"{ORDERS}/{r['id']}/confirm", headers=pa)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "paid"

    rows = _orders_of(db_session, tid)
    assert all(r["status"] == "paid" for r in rows)  # 两张均 paid（不可逆）
    quota = _tenant_state(db_session, tid)["quota"]
    assert quota == PRO_QUOTA  # 配额=专业档一套三数字，不因第二张叠档
    assert quota["task_concurrency"] == 20  # 不是 40（叠加会翻倍）


def test_gwt_92_1_submitted_event_with_tenant_and_plan(db_client, db_session, db_engine):
    from conftest import make_platform_admin_headers, make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t02-921")
    pa = make_platform_admin_headers(db_session)
    _submit_pro(db_client, owner)

    events = _events_of(db_session, "offline_order_submitted", tid)
    assert len(events) == 1
    assert events[0].tenant_id == tid
    assert events[0].props["plan_name"] == "专业档"
    assert "sk-" not in str(events[0].props)  # 不含明文/密钥

    face = db_client.get(
        EVENTS_QUERY, headers=pa,
        params={"event_name": "offline_order_submitted", "tenant_id": tid},
    )
    assert face.status_code == 200, face.text
    body = face.json()["data"]
    assert body["total"] >= 1
    assert any(
        i["props"] and i["props"].get("plan_name") == "专业档" for i in body["items"]
    )  # 超管查询面可查


def test_gwt_92_2_confirmed_event_with_tenant_and_plan(db_client, db_session, db_engine):
    from conftest import make_platform_admin_headers, make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t02-922")
    pa = make_platform_admin_headers(db_session)
    order = _submit_pro(db_client, owner)
    resp = db_client.post(f"{ORDERS}/{order['id']}/confirm", headers=pa)
    assert resp.status_code == 200

    events = _events_of(db_session, "offline_order_confirmed", tid)
    assert len(events) == 1
    assert events[0].tenant_id == tid
    assert events[0].props["plan_name"] == "专业档"
    assert "sk-" not in str(events[0].props)
