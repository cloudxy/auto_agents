"""T-13 / FR-18：无工人拦住入队；提交后掉线 120s 可见空态。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from conftest import make_tenant_owner_headers
from platform_core.models.spider_task import SpiderTask
from platform_core.tenant_context import tenant_scope
from sqlalchemy import select
from stubs import FakeRedis, seed_worker_heartbeat

RUN_URL = "/api/v1/spiders/run"


def _patch_redis(monkeypatch, *, worker: bool = True) -> FakeRedis:
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


def test_submit_without_worker_blocked_or_spider_worker_offline(
    db_client, db_engine, db_session, monkeypatch,
):
    """GWT-18.2：无在线工人 → 拦住或立即 SPIDER_WORKER_OFFLINE，不假装在爬。"""
    _patch_redis(monkeypatch, worker=False)
    headers, _tid = make_tenant_owner_headers(db_session, slug="t13off")
    resp = db_client.post(
        RUN_URL,
        json={"spider_name": "example", "params": '{"urls": ["https://httpbin.org/get"]}'},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["code"] == "SPIDER_WORKER_OFFLINE"
    assert "采集未运行，不会出数" in body["message"]

    async def _check():
        async with db_session() as s:
            rows = (await s.execute(select(SpiderTask))).scalars().all()
            assert rows == []

    asyncio.run(_check())


def test_worker_offline_after_submit_visible_within_120s(
    db_client, db_engine, db_session, monkeypatch,
):
    """GWT-18.4：提交后工人掉线，无终态满 120s → 任务上可见工人不在线。"""
    fake = _patch_redis(monkeypatch, worker=True)
    headers, tid = make_tenant_owner_headers(db_session, slug="t13drop")
    resp = db_client.post(
        RUN_URL,
        json={"spider_name": "example", "params": '{"urls": ["https://httpbin.org/get"]}'},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["data"]["id"]
    fake.hashes.clear()

    async def _age():
        with tenant_scope(tid):
            async with db_session() as s:
                task = await s.get(SpiderTask, task_id)
                assert task is not None
                task.created_at = datetime.now(timezone.utc) - timedelta(seconds=121)
                await s.commit()

    asyncio.run(_age())
    listing = db_client.get("/api/v1/spiders/tasks", headers=headers)
    assert listing.status_code == 200, listing.text
    row = next(i for i in listing.json()["data"]["items"] if i["id"] == task_id)
    assert row["status"] not in ("completed", "failed")
    assert row["worker_offline"] is True
    assert "采集未运行，不会出数" in (row.get("error_message") or "")
