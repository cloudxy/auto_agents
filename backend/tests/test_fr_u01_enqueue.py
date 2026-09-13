"""T-02 / FR-U01 FR-U02：空非夹具租户入队、本企业结果、工人空态句、拦住事件。

GWT-U01.1 入队+本企业出数 / U01.2 空结果句 / U01.3 跨租户同形不存在
/ U02.1 无工人 3s 拦住。配额句仍由 T-03 覆盖；本票补 task_blocked 可查。
禁止支付宝 notify / 中转 SKU。
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

from sqlalchemy import select

from platform_core.models.internal_fixture_tenant import InternalFixtureTenant
from platform_core.models.spider_result import SpiderResult
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

RUN_URL = "/api/v1/spiders/run"
RESULTS_URL = "/api/v1/spiders/results"
EVENTS_URL = "/api/v1/product-events"
HTTPBIN_URL = "https://httpbin.org/get"
CALLBACK_URL = "/external/v1/webhooks/spider/callback"

ENQUEUED = "已入队"
EMPTY_COPY = "还没有结果，去提交采集"
WORKER_COPY = "采集未运行，不会出数"
LOAD_FAIL = "加载失败"
RUNNING_COPY = "正在采集"
PLAN_FULL = "已达配额上限"


def _seed_worker_redis(monkeypatch, *, worker: bool = True):
    from stubs import FakeRedis, seed_worker_heartbeat

    fake = FakeRedis()
    if worker:
        seed_worker_heartbeat(fake)

    def _get(key=None):
        return fake

    import backend.services.quota_service as quota_mod
    import backend.services.spider_task_service as svc_mod

    monkeypatch.setattr(svc_mod, "get_async_redis", _get)
    monkeypatch.setattr(quota_mod, "get_async_redis", _get)
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


def _event_items(db_client, headers, **params) -> list:
    resp = db_client.get(
        EVENTS_URL, headers=headers,
        params={k: v for k, v in params.items() if v is not None},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["items"]


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


def _set_quota(db_session, tid: int, **quota) -> None:
    async def _go():
        async with db_session() as s:
            tenant = (await s.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
            tenant.quota = quota
            await s.commit()

    asyncio.run(_go())


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
                url=HTTPBIN_URL, title="owned-a", tenant_id=tid,
            ))
            await s.commit()

    asyncio.run(_go())


def test_gwt_u01_1_empty_non_fixture_enqueues_and_results_stay_in_tenant(
    db_client, db_engine, db_session, monkeypatch,
):
    """GWT-U01.1：空非夹具企业提交 example/httpbin → 3s 已入队；结果只在本企业。"""
    from conftest import make_platform_admin_headers, make_tenant_owner_headers

    fake = _seed_worker_redis(monkeypatch, worker=True)
    headers_a, tid_a = make_tenant_owner_headers(db_session, slug="u01-1a")
    headers_b, _tid_b = make_tenant_owner_headers(db_session, slug="u01-1b")
    op = _member_headers(db_session, tid_a, "operator", "u01-1-op")
    assert tid_a not in _fixture_ids(db_session)
    assert _tasks_of(db_session, tid_a) == []

    started = time.monotonic()
    resp = db_client.post(
        RUN_URL, headers=op,
        json={"spider_name": "example", "params": json.dumps({"urls": [HTTPBIN_URL]})},
    )
    elapsed = time.monotonic() - started
    assert resp.status_code == 200, resp.text
    assert elapsed <= 3
    body = resp.json()
    assert ENQUEUED in body["message"]
    task_id = body["data"]["id"]
    assert body["data"]["status"] in ("pending", "queued")
    assert body["data"]["status"] != "running"
    rows = _tasks_of(db_session, tid_a)
    assert len(rows) == 1 and int(rows[0].id) == task_id

    asyncio.run(_ingest_flush(fake, db_engine, task_id))
    assert _webhook_complete(db_client, task_id).status_code == 200

    mine = db_client.get(f"{RESULTS_URL}/{task_id}", headers=headers_a)
    assert mine.status_code == 200, mine.text
    mine_data = mine.json()["data"]
    assert mine_data["total"] > 0
    assert any(HTTPBIN_URL in (i.get("url") or "") for i in mine_data["items"])

    dc_a = db_client.get(RESULTS_URL, headers=headers_a)
    assert dc_a.status_code == 200
    assert dc_a.json()["data"]["total"] > 0

    dc_b = db_client.get(RESULTS_URL, headers=headers_b)
    assert dc_b.status_code == 200
    blob_b = dc_b.text
    assert HTTPBIN_URL not in blob_b
    assert "owned-a" not in blob_b
    assert all(
        (i.get("url") or "") != HTTPBIN_URL for i in dc_b.json()["data"]["items"]
    )

    admin = make_platform_admin_headers(db_session)
    done = [
        r for r in _event_items(db_client, admin, event_name="task_completed", tenant_id=tid_a)
        if r["event_name"] == "task_completed"
    ]
    blocked = [
        r for r in _event_items(db_client, admin, event_name="task_blocked", tenant_id=tid_a)
        if r["event_name"] == "task_blocked"
    ]
    assert done
    assert done[0]["is_internal_fixture"] is False
    assert done[0]["props"]["result_count"] > 0
    assert done[0]["props"]["is_marketplace_candidate"] is False
    assert not any((r.get("props") or {}).get("result_count", 0) > 0 for r in blocked)


def test_gwt_u01_2_empty_results_copy_is_actionable(db_client, db_session):
    """GWT-U01.2：尚无任务时「我的结果」为 0 条 + 去提交采集；禁止空白/加载失败装 0。"""
    from conftest import make_tenant_owner_headers

    headers, tid = make_tenant_owner_headers(db_session, slug="u01-2")
    assert _tasks_of(db_session, tid) == []
    resp = db_client.get(RESULTS_URL, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["total"] == 0
    assert body["data"]["items"] == []
    message = body["message"] or ""
    assert message.strip() != ""
    assert "还没有结果" in message
    assert "去提交采集" in message
    assert LOAD_FAIL not in message
    assert LOAD_FAIL not in resp.text


def test_gwt_u01_3_cross_tenant_result_same_as_missing(db_client, db_session):
    """GWT-U01.3：企业 B 打开企业 A 的结果 = 页面不存在同形，无 A 字段。"""
    from conftest import make_tenant_owner_headers

    headers_a, tid_a = make_tenant_owner_headers(db_session, slug="u01-3a")
    headers_b, _tid_b = make_tenant_owner_headers(db_session, slug="u01-3b")
    _seed_owned_result(db_session, tid_a)

    own = db_client.get(RESULTS_URL, headers=headers_a)
    assert own.status_code == 200
    assert own.json()["data"]["total"] >= 1
    task_id = int(_tasks_of(db_session, tid_a)[0].id)

    missing = db_client.get(f"{RESULTS_URL}/99999999", headers=headers_b)
    other = db_client.get(f"{RESULTS_URL}/{task_id}", headers=headers_b)
    assert missing.status_code == 404
    assert other.status_code == missing.status_code
    assert other.json()["code"] == missing.json()["code"] == "NOT_FOUND"
    assert HTTPBIN_URL not in other.text
    assert "owned-a" not in other.text
    assert "抱歉您没有权限" not in other.text

    dc_b = db_client.get(RESULTS_URL, headers=headers_b)
    assert dc_b.status_code == 200
    assert HTTPBIN_URL not in dc_b.text
    assert "owned-a" not in dc_b.text


def test_gwt_u02_1_worker_offline_blocks_within_3s_and_emits_task_blocked(
    db_client, db_session, monkeypatch,
):
    """GWT-U02.1：无在线工人 → 3s 内「采集未运行，不会出数」；不入队；可查拦住。"""
    from conftest import make_platform_admin_headers, make_tenant_owner_headers

    _seed_worker_redis(monkeypatch, worker=False)
    _headers, tid = make_tenant_owner_headers(db_session, slug="u02-1")
    op = _member_headers(db_session, tid, "operator", "u02-1-op")
    assert tid not in _fixture_ids(db_session)

    started = time.monotonic()
    resp = db_client.post(
        RUN_URL, headers=op,
        json={"spider_name": "example", "params": json.dumps({"urls": [HTTPBIN_URL]})},
    )
    elapsed = time.monotonic() - started
    assert elapsed <= 3
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["code"] == "SPIDER_WORKER_OFFLINE"
    assert WORKER_COPY in body["message"]
    assert PLAN_FULL not in body["message"]
    assert RUNNING_COPY not in body["message"]
    assert LOAD_FAIL not in body["message"]
    assert _tasks_of(db_session, tid) == []

    admin = make_platform_admin_headers(db_session)
    blocked = [
        r for r in _event_items(db_client, admin, event_name="task_blocked", tenant_id=tid)
        if r["event_name"] == "task_blocked"
    ]
    done = [
        r for r in _event_items(db_client, admin, event_name="task_completed", tenant_id=tid)
        if r["event_name"] == "task_completed"
    ]
    submitted = [
        r for r in _event_items(db_client, admin, event_name="task_run_submitted", tenant_id=tid)
        if r["event_name"] == "task_run_submitted"
    ]
    assert len(blocked) == 1
    assert blocked[0]["props"]["reason"] == "worker_offline"
    assert blocked[0]["is_internal_fixture"] is False
    assert not any((r.get("props") or {}).get("result_count", 0) > 0 for r in done)
    assert submitted == []


def test_storage_full_emits_task_blocked_not_completed(
    db_client, db_session, monkeypatch,
):
    """拦住 vs 完成：存储满入队发 task_blocked(quota_storage)，无合格 completed。"""
    from conftest import make_platform_admin_headers, make_tenant_owner_headers

    _seed_worker_redis(monkeypatch, worker=True)
    _headers, tid = make_tenant_owner_headers(db_session, slug="u02-blk")
    op = _member_headers(db_session, tid, "operator", "u02-blk-op")
    _set_quota(db_session, tid, result_storage=1, llm_tokens_month=999999, task_concurrency=20)
    _seed_owned_result(db_session, tid)
    before = len(_tasks_of(db_session, tid))

    resp = db_client.post(
        RUN_URL, headers=op,
        json={"spider_name": "example", "params": json.dumps({"urls": [HTTPBIN_URL]})},
    )
    assert resp.status_code == 400, resp.text
    assert PLAN_FULL in resp.json()["message"]
    assert WORKER_COPY not in resp.json()["message"]
    assert len(_tasks_of(db_session, tid)) == before

    admin = make_platform_admin_headers(db_session)
    blocked = [
        r for r in _event_items(db_client, admin, event_name="task_blocked", tenant_id=tid)
        if r["event_name"] == "task_blocked"
    ]
    done = [
        r for r in _event_items(db_client, admin, event_name="task_completed", tenant_id=tid)
        if r["event_name"] == "task_completed"
        and (r.get("props") or {}).get("result_count", 0) > 0
    ]
    assert blocked
    assert blocked[0]["props"]["reason"] == "quota_storage"
    assert blocked[0]["is_internal_fixture"] is False
    assert done == []
