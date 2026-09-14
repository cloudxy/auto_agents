"""T-03 / FR-U02：配额已尽/将满句；申请提升分角色（不建支付单）。

GWT-U02.2 存储满入队 / U02.3 只读提交 / U02.4 token 满规划
/ U02.5 将满用量 / U02.6 经办只读申请提升 / U02.7 买方结账路由。
工人句与配额句不得混用；可见处无 QUOTA_EXCEEDED、无裸 429。
"""
from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from platform_core.models.billing import Order
from platform_core.models.llm_token_usage import LlmTokenUsage
from platform_core.models.spider_result import SpiderResult
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

RUN_URL = "/api/v1/spiders/run"
USAGE_URL = "/api/v1/tenants/me/usage"
UPGRADE_URL = "/api/v1/tenants/me/quota/upgrade-intent"
CHECKOUT_URL = "/api/v1/billing/checkout"
PLAN_URL = "/api/v1/ai/plans"

WORKER_COPY = "采集未运行，不会出数"
PLAN_FULL = "已达配额上限"
NEAR_COPY = "接近上限。超额操作会被拒绝。"
UPGRADE_CTA = "申请提升"
STORAGE_CTA = "去结果库"
CONTACT_ADMIN = "请联系本企业管理员开通"
CHECKOUT_EMPTY = "收款通道未开通"
CHECKOUT_PATH = "/billing/checkout?product=plan_pro"

_FORBIDDEN_CODES = {"FORBIDDEN", "QUOTA_EXCEEDED", "QUOTA_PLAN_LOCKED", "HTTP_403", "HTTP_429"}
_VISIBLE_TOKENS = ("QUOTA_EXCEEDED", "QUOTA_PLAN_LOCKED", "FORBIDDEN", "PAYMENT_NOT_CONFIGURED")


def _seed_worker_redis(monkeypatch):
    from stubs import FakeRedis, seed_worker_heartbeat

    fake = FakeRedis()
    seed_worker_heartbeat(fake)

    import backend.services.quota_service as quota_mod
    import backend.services.spider_task_service as svc_mod

    monkeypatch.setattr(svc_mod, "get_async_redis", lambda: fake)
    monkeypatch.setattr(quota_mod, "get_async_redis", lambda: fake)
    return fake


def _assert_no_inner_code(resp) -> None:
    assert resp.status_code != 429, resp.text
    body = resp.json()
    assert body["code"] not in _FORBIDDEN_CODES, body["code"]
    blob = str(body)
    for token in _VISIBLE_TOKENS:
        assert token not in blob, blob
    assert "429" not in body.get("message", "")


def _set_quota(db_session, tid: int, **quota) -> None:
    async def _go():
        async with db_session() as s:
            tenant = (await s.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
            tenant.quota = quota
            await s.commit()

    asyncio.run(_go())


def _member_headers(db_session, tid: int, tenant_role: str, username: str) -> dict:
    from backend.services.auth_service import AuthService

    role = "viewer" if tenant_role == "viewer" else (
        "admin" if tenant_role in ("owner", "admin") else "operator"
    )

    async def _go():
        async with db_session() as s:
            s.add(User(
                username=username, email=f"{username}@x.co", password_hash="x",
                role=role, tenant_id=tid, tenant_role=tenant_role, is_active=True,
            ))
            await s.commit()
            u = (await s.execute(select(User).where(User.username == username))).scalar_one()
            token = await AuthService(s).create_token({
                "id": u.id, "username": u.username, "is_admin": tenant_role in ("owner", "admin"),
                "role": role, "tenant_id": tid, "tenant_role": tenant_role,
                "is_platform_admin": False,
            })
            return token.access_token

    return {"Authorization": f"Bearer {asyncio.run(_go())}"}


def _tasks_of(db_session, tid: int) -> list:
    async def _go():
        async with db_session() as s:
            return (await s.execute(
                select(SpiderTask).where(SpiderTask.tenant_id == tid)
            )).scalars().all()

    return asyncio.run(_go())


def _orders_of(db_session, tid: int) -> list:
    async def _go():
        async with db_session() as s:
            return (await s.execute(
                select(Order).where(Order.tenant_id == tid)
            )).scalars().all()

    return asyncio.run(_go())


def _order_count(db_session) -> int:
    async def _go():
        async with db_session() as s:
            return int((await s.execute(select(func.count()).select_from(Order))).scalar_one())

    return asyncio.run(_go())


def _seed_owned_result(db_session, tid: int) -> None:
    async def _go():
        async with db_session() as s:
            task = SpiderTask(
                spider_name="example", tenant_id=tid, status="completed", params="{}",
            )
            s.add(task)
            await s.flush()
            s.add(SpiderResult(
                task_id=int(task.id), spider_name="example",
                url="https://httpbin.org/get", tenant_id=tid,
            ))
            await s.commit()

    asyncio.run(_go())


def _seed_token_usage(db_session, tid: int, tokens: int) -> None:
    from backend.services.quota_service import shanghai_today

    async def _go():
        async with db_session() as s:
            s.add(LlmTokenUsage(
                tenant_id=tid, provider_name="provider:1", model="m",
                stat_date=shanghai_today(), total_tokens=tokens,
            ))
            await s.commit()

    asyncio.run(_go())


def test_gwt_u02_2_storage_full_blocks_enqueue_with_results_cta(
    db_client, db_session, monkeypatch,
):
    """GWT-U02.2：工人在线、存储已满 → 已达配额上限 + 去结果库；不入队；非工人句。"""
    from conftest import make_tenant_owner_headers

    _seed_worker_redis(monkeypatch)
    _headers, tid = make_tenant_owner_headers(db_session, slug="u02-2")
    op = _member_headers(db_session, tid, "operator", "u02-2-op")
    _set_quota(db_session, tid, result_storage=1, llm_tokens_month=999999, task_concurrency=20)
    _seed_owned_result(db_session, tid)
    before = len(_tasks_of(db_session, tid))

    resp = db_client.post(
        RUN_URL, headers=op,
        json={"spider_name": "example", "params": '{"urls": ["https://httpbin.org/get"]}'},
    )
    _assert_no_inner_code(resp)
    body = resp.json()
    assert PLAN_FULL in body["message"]
    assert STORAGE_CTA in body["message"]
    assert UPGRADE_CTA not in body["message"]
    assert WORKER_COPY not in body["message"]
    assert len(_tasks_of(db_session, tid)) == before


def test_gwt_u02_3_readonly_submit_rejected_no_enqueue(db_client, db_session):
    """GWT-U02.3：只读提交采集 → 拒绝；不入队。"""
    from conftest import make_tenant_owner_headers

    _headers, tid = make_tenant_owner_headers(db_session, slug="u02-3")
    viewer = _member_headers(db_session, tid, "viewer", "u02-3-ro")

    resp = db_client.post(
        RUN_URL, headers=viewer,
        json={"spider_name": "example", "params": "{}"},
    )
    _assert_no_inner_code(resp)
    assert "不能提交" in resp.json()["message"]
    assert _tasks_of(db_session, tid) == []


def test_gwt_u02_4_token_full_planning_is_quota_copy_not_worker(
    db_client, db_session,
):
    """GWT-U02.4：token 已满、存储未满 → 规划可见已达配额上限 + 申请提升；非工人句。"""
    from config import settings
    from conftest import make_tenant_owner_headers

    prev = settings.get("LLM.ENABLED")
    settings.set("LLM.ENABLED", True)
    try:
        _headers, tid = make_tenant_owner_headers(db_session, slug="u02-4")
        op = _member_headers(db_session, tid, "operator", "u02-4-op")
        _set_quota(db_session, tid, llm_tokens_month=100, result_storage=10000, task_concurrency=20)
        _seed_token_usage(db_session, tid, 100)

        created = db_client.post(
            PLAN_URL, headers=op,
            json={"target_url": "https://example.com/list", "html_snippet": "<html><h1>t</h1></html>"},
        )
        assert created.status_code in (200, 201), created.text
        pid = created.json()["data"]["id"]

        resp = db_client.post(f"{PLAN_URL}/{pid}/plan", headers=op)
        _assert_no_inner_code(resp)
        body = resp.json()
        assert PLAN_FULL in body["message"]
        assert UPGRADE_CTA in body["message"]
        assert WORKER_COPY not in body["message"]
        assert STORAGE_CTA not in body["message"]

        snap = db_client.get(f"{PLAN_URL}/{pid}", headers=op)
        assert snap.status_code == 200
        assert snap.json()["data"]["status"] == "draft"
    finally:
        settings.set("LLM.ENABLED", prev)


def test_gwt_u02_5_usage_near_limit_is_not_full_copy(db_client, db_session):
    """GWT-U02.5：token ≥90% 未满 → 将满句；不是已达上限；无申请提升当满额出口。"""
    from conftest import make_tenant_owner_headers

    headers, tid = make_tenant_owner_headers(db_session, slug="u02-5")
    _set_quota(db_session, tid, llm_tokens_month=100)
    _seed_token_usage(db_session, tid, 90)

    resp = db_client.get(USAGE_URL, headers=headers)
    assert resp.status_code == 200, resp.text
    _assert_no_inner_code(resp)
    data = resp.json()["data"]
    blob = str(data)
    assert "QUOTA_EXCEEDED" not in blob
    near = [a for a in data["alerts"] if a["level"] == "near"]
    assert near and near[0]["message"] == NEAR_COPY
    assert PLAN_FULL not in [a["message"] for a in data["alerts"]]
    assert all(not a.get("cta") for a in near)


def test_gwt_u02_6_operator_upgrade_intent_contact_admin_no_order(
    db_client, db_session,
):
    """GWT-U02.6：经办点申请提升 → 联系本企业管理员；不建单；不到结账。"""
    from conftest import make_tenant_owner_headers

    _headers, tid = make_tenant_owner_headers(db_session, slug="u02-6o")
    op = _member_headers(db_session, tid, "operator", "u02-6-op")
    before = _order_count(db_session)

    resp = db_client.get(UPGRADE_URL, headers=op)
    assert resp.status_code == 200, resp.text
    _assert_no_inner_code(resp)
    data = resp.json()["data"]
    assert data["action"] == "contact_admin"
    assert CONTACT_ADMIN in data["message"]
    assert data.get("checkout_path") in (None, "")
    assert "/register" not in str(data)
    assert _orders_of(db_session, tid) == []
    assert _order_count(db_session) == before


def test_gwt_u02_6_viewer_upgrade_intent_contact_admin_no_order(
    db_client, db_session,
):
    """GWT-U02.6：只读点申请提升 → 联系本企业管理员；不建单。"""
    from conftest import make_tenant_owner_headers

    _headers, tid = make_tenant_owner_headers(db_session, slug="u02-6v")
    viewer = _member_headers(db_session, tid, "viewer", "u02-6-ro")
    before = _order_count(db_session)

    resp = db_client.get(UPGRADE_URL, headers=viewer)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["action"] == "contact_admin"
    assert CONTACT_ADMIN in data["message"]
    assert data.get("checkout_path") in (None, "")
    assert _order_count(db_session) == before


def test_gwt_u02_7_buyer_upgrade_intent_checkout_path_no_order(
    db_client, db_session,
):
    """GWT-U02.7：买方点申请提升 → 稳定结账路由；不建支付单；非联系说明唯一出口。"""
    from conftest import make_tenant_owner_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="u02-7")
    before = _order_count(db_session)

    resp = db_client.get(f"{UPGRADE_URL}?product=plan_pro", headers=owner)
    assert resp.status_code == 200, resp.text
    _assert_no_inner_code(resp)
    data = resp.json()["data"]
    assert data["action"] == "checkout"
    assert data["product"] == "plan_pro"
    assert data["checkout_path"] == CHECKOUT_PATH
    assert CONTACT_ADMIN not in data["message"]
    assert "/register" not in str(data)
    assert _orders_of(db_session, tid) == []
    assert _order_count(db_session) == before


def test_gwt_u02_7_buyer_checkout_empty_state_creates_no_order(
    db_client, db_session,
):
    """W2：买方打开结账不建单；未配通道仍可见商品（GWT-U32.2 已作废）。"""
    from conftest import make_tenant_owner_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="u02-7c")
    before = _order_count(db_session)

    resp = db_client.get(f"{CHECKOUT_URL}?product=plan_pro", headers=owner)
    assert resp.status_code != 429, resp.text
    body = resp.json()
    assert body["data"]["product"] == "plan_pro"
    assert body["data"]["order_id"] is None
    assert "当前可买" not in str(body)
    assert "QUOTA_EXCEEDED" not in str(body)
    assert _orders_of(db_session, tid) == []
    assert _order_count(db_session) == before


def test_operator_checkout_get_contact_admin_no_order(db_client, db_session):
    """经办直打开结账 → 联系管理员；不建单。"""
    from conftest import make_tenant_owner_headers

    _headers, tid = make_tenant_owner_headers(db_session, slug="u02-7o")
    op = _member_headers(db_session, tid, "operator", "u02-7-op")
    before = _order_count(db_session)

    resp = db_client.get(f"{CHECKOUT_URL}?product=plan_pro", headers=op)
    _assert_no_inner_code(resp)
    body = resp.json()
    assert CONTACT_ADMIN in body["message"]
    assert _orders_of(db_session, tid) == []
    assert _order_count(db_session) == before


def test_concurrency_full_enqueue_uses_upgrade_cta_not_worker(
    db_client, db_session, monkeypatch,
):
    """屏6：并发已满 → 已达配额上限 + 申请提升；不是工人句、不是去结果库。"""
    from conftest import make_tenant_owner_headers

    _seed_worker_redis(monkeypatch)
    headers, tid = make_tenant_owner_headers(db_session, slug="u02-cc")
    _set_quota(db_session, tid, task_concurrency=1, result_storage=10000)

    async def _seed():
        async with db_session() as s:
            s.add(SpiderTask(
                spider_name="example", tenant_id=tid, status="running", params="{}",
            ))
            await s.commit()

    asyncio.run(_seed())

    resp = db_client.post(
        RUN_URL, headers=headers,
        json={"spider_name": "example", "params": "{}"},
    )
    _assert_no_inner_code(resp)
    body = resp.json()
    assert PLAN_FULL in body["message"]
    assert UPGRADE_CTA in body["message"]
    assert WORKER_COPY not in body["message"]
    assert STORAGE_CTA not in body["message"]
    assert len(_tasks_of(db_session, tid)) == 1
