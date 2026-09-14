"""T-03 / FR-M03：空免费非夹具企业第一次采集无付费/订阅/中转前置；只读拒绝。

GWT-M03.1 入队（夹具 example/httpbin；完成态在本进程 ingest，C4 真工人见 evidence）
/ M03.2 空态可见提交、无付费墙 / M03.3 只读拒绝。
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

from sqlalchemy import func, select

from platform_core.models.billing import Order
from platform_core.models.capability import CapabilityInstall
from platform_core.models.internal_fixture_tenant import InternalFixtureTenant
from platform_core.models.relay_sku_entitlement import RelaySkuEntitlement
from platform_core.models.spider_task import SpiderTask
from platform_core.models.user import User

RUN_URL = "/api/v1/spiders/run"
TASKS_URL = "/api/v1/spiders/tasks"
RESULTS_URL = "/api/v1/spiders/results"
HTTPBIN_URL = "https://httpbin.org/get"
CALLBACK_URL = "/external/v1/webhooks/spider/callback"
ENQUEUED = "已入队"
PAYWALL = ("请先开通专业档", "请先订阅能力")
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


def _fixture_ids(db_session) -> set[int]:
    async def _go():
        async with db_session() as s:
            rows = (await s.execute(select(InternalFixtureTenant.tenant_id))).scalars().all()
            return {int(x) for x in rows}

    return asyncio.run(_go())


def _count(db_session, model, tid: int, **filters) -> int:
    async def _go():
        async with db_session() as s:
            stmt = select(func.count()).select_from(model).where(model.tenant_id == tid)
            for key, value in filters.items():
                stmt = stmt.where(getattr(model, key) == value)
            return int((await s.execute(stmt)).scalar_one())

    return asyncio.run(_go())


def _assert_empty_free_non_fixture(db_session, tid: int) -> None:
    assert tid not in _fixture_ids(db_session)
    assert _tasks_of(db_session, tid) == []
    assert _count(db_session, CapabilityInstall, tid) == 0
    assert _count(db_session, RelaySkuEntitlement, tid, status="active") == 0
    paid = _count(db_session, Order, tid, status="fulfilled") + _count(
        db_session, Order, tid, status="paid",
    )
    assert paid == 0


def _assert_no_inner_code(resp) -> None:
    assert resp.status_code != 429, resp.text
    body = resp.json()
    assert body["code"] not in _FORBIDDEN_CODES, body["code"]
    blob = str(body)
    for token in _VISIBLE_TOKENS:
        assert token not in blob, blob
    for wall in PAYWALL:
        assert wall not in blob, blob


def _webhook_complete(client, task_id: int):
    from config import settings

    body = json.dumps({"task_id": task_id, "status": "completed"}).encode()
    ts = str(int(time.time()))
    secret = str(settings.WEBHOOK.SECRET_KEY)
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return client.post(
        CALLBACK_URL, content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Timestamp": ts,
            "X-Webhook-Signature": sig,
        },
    )


async def _ingest_flush(fake, engine, task_id: int) -> None:
    from platform_core.queues import ITEM_QUEUE
    from backend.tasks.consumer import SpiderTaskConsumer

    message = json.dumps(
        {
            "task_id": task_id,
            "spider_name": "example",
            "item_type": "BaseItem",
            "item": {
                "url": HTTPBIN_URL,
                "title": "API Response from https://httpbin.org/get",
                "content": '{"url": "https://httpbin.org/get"}',
                "source": "api",
            },
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        ensure_ascii=False,
    )
    await fake.rpush(ITEM_QUEUE, message)
    consumer = SpiderTaskConsumer()
    consumer._redis = fake
    consumer._engine = lambda: engine
    raws = await fake.lpop(ITEM_QUEUE, count=20)
    assert raws, "ITEM_QUEUE empty"
    messages = [json.loads(raw) for raw in raws]
    counts: dict[int, int] = {}
    for msg in messages:
        tid = msg["task_id"]
        counts[tid] = counts.get(tid, 0) + 1
    await consumer._flush_batch(messages, counts)


def test_gwt_m03_1_empty_free_non_fixture_enqueues_without_paywall(
    db_client, db_engine, db_session, monkeypatch,
):
    """GWT-M03.1：空免费非夹具企业提交 example/httpbin → 3s 已入队；结果只在本企业。

    完成态走本进程 ingest+webhook（与 FR-U01 同缝）。C4 真 Scrapy 工人 120s
    出数是环境闸，本套件不假装 live worker 在线。
    """
    from conftest import make_tenant_owner_headers

    fake = _seed_worker_redis(monkeypatch)
    headers_a, tid_a = make_tenant_owner_headers(db_session, slug="m03-1a")
    headers_b, _tid_b = make_tenant_owner_headers(db_session, slug="m03-1b")
    op = _member_headers(db_session, tid_a, "operator", "m03-1-op")
    _assert_empty_free_non_fixture(db_session, tid_a)

    started = time.monotonic()
    resp = db_client.post(
        RUN_URL, headers=op,
        json={"spider_name": "example", "params": json.dumps({"urls": [HTTPBIN_URL]})},
    )
    elapsed = time.monotonic() - started
    assert elapsed <= 3
    assert resp.status_code == 200, resp.text
    _assert_no_inner_code(resp)
    body = resp.json()
    assert ENQUEUED in body["message"]
    task_id = body["data"]["id"]
    rows = _tasks_of(db_session, tid_a)
    assert len(rows) == 1 and int(rows[0].id) == task_id

    asyncio.run(_ingest_flush(fake, db_engine, task_id))
    assert _webhook_complete(db_client, task_id).status_code == 200

    mine = db_client.get(f"{RESULTS_URL}/{task_id}", headers=headers_a)
    assert mine.status_code == 200, mine.text
    assert mine.json()["data"]["total"] > 0
    other = db_client.get(RESULTS_URL, headers=headers_b)
    assert HTTPBIN_URL not in other.text


def test_gwt_m03_2_task_list_has_no_paywall_copy(db_client, db_session):
    """GWT-M03.2：尚无任务时列表成功；无「请先开通专业档 / 请先订阅能力」。"""
    from conftest import make_tenant_owner_headers

    headers, tid = make_tenant_owner_headers(db_session, slug="m03-2")
    _assert_empty_free_non_fixture(db_session, tid)
    resp = db_client.get(TASKS_URL, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["total"] == 0
    blob = resp.text
    for wall in PAYWALL:
        assert wall not in blob


def test_gwt_m03_3_viewer_submit_rejected_no_enqueue(db_client, db_session):
    """GWT-M03.3：只读提交采集 → 拒绝；不入队。"""
    from conftest import make_tenant_owner_headers

    _headers, tid = make_tenant_owner_headers(db_session, slug="m03-3")
    viewer = _member_headers(db_session, tid, "viewer", "m03-3-ro")
    resp = db_client.post(
        RUN_URL, headers=viewer,
        json={"spider_name": "example", "params": json.dumps({"urls": [HTTPBIN_URL]})},
    )
    _assert_no_inner_code(resp)
    assert "不能提交" in resp.json()["message"]
    assert _tasks_of(db_session, tid) == []
