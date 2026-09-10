"""T-13 / FR-19：零条目离开运行中；跨租户 0 条任务与不存在同形。"""
from __future__ import annotations

import asyncio

from conftest import make_tenant_owner_headers
from platform_core.models.spider_task import SpiderTask
from platform_core.tenant_context import tenant_scope
from stubs import FakeRedis, seed_worker_heartbeat


def _patch_redis(monkeypatch) -> FakeRedis:
    fake = FakeRedis()
    seed_worker_heartbeat(fake)

    def _get(key=None):
        return fake

    import backend.services.spider_task_service as svc_mod

    monkeypatch.setattr(svc_mod, "get_async_redis", _get)
    return fake


def test_zero_items_leaves_running_not_blank(
    db_client, db_engine, db_session, monkeypatch,
):
    """GWT-19.1 / 19.2：0 条收尾离开运行中；打开任务能看到 0 条而非空白无说明。"""
    _patch_redis(monkeypatch)
    headers, tid = make_tenant_owner_headers(db_session, slug="t13zero")

    async def _go() -> int:
        from backend.services.spider_query_service import SpiderQueryService
        from backend.services.spider_task_service import SpiderTaskService

        with tenant_scope(tid):
            async with db_session() as s:
                task = SpiderTask(
                    spider_name="example",
                    tenant_id=tid,
                    status="running",
                    params="{}",
                    result_count=0,
                )
                s.add(task)
                await s.commit()
                await s.refresh(task)
                finished = await SpiderTaskService(s).finish_task(
                    task.id, "completed", item_count=0,
                )
                assert finished.status in ("completed", "failed")
                assert finished.status != "running"
                assert finished.result_count == 0
                results = await SpiderQueryService(s).list_results(task.id)
                assert results.total == 0
                return int(task.id)

    task_id = asyncio.run(_go())
    listing = db_client.get("/api/v1/spiders/tasks", headers=headers)
    assert listing.status_code == 200, listing.text
    row = next(i for i in listing.json()["data"]["items"] if i["id"] == task_id)
    assert row["status"] != "running"
    assert row["result_count"] == 0
    results = db_client.get(f"/api/v1/spiders/results/{task_id}", headers=headers)
    assert results.status_code == 200, results.text
    body = results.json()
    assert body["data"]["total"] == 0
    assert body["data"]["items"] == []


def test_tenant_b_zero_item_task_same_as_missing(
    db_client, db_engine, db_session, monkeypatch,
):
    """GWT-19.3：企业 B 打开企业 A 的 0 条任务，与不存在同形。"""
    _patch_redis(monkeypatch)
    headers_a, ta = make_tenant_owner_headers(db_session, slug="t13za")
    headers_b, _tb = make_tenant_owner_headers(db_session, slug="t13zb")

    async def _go() -> int:
        with tenant_scope(ta):
            async with db_session() as s:
                task = SpiderTask(
                    spider_name="example",
                    tenant_id=ta,
                    status="completed",
                    params="{}",
                    result_count=0,
                )
                s.add(task)
                await s.commit()
                await s.refresh(task)
                return int(task.id)

    task_id = asyncio.run(_go())
    missing = db_client.get("/api/v1/spiders/results/99999999", headers=headers_b)
    other = db_client.get(f"/api/v1/spiders/results/{task_id}", headers=headers_b)
    assert missing.status_code == 404
    assert other.status_code == missing.status_code
    assert other.json()["code"] == missing.json()["code"] == "NOT_FOUND"
    own = db_client.get(f"/api/v1/spiders/results/{task_id}", headers=headers_a)
    assert own.status_code == 200, own.text
    assert own.json()["data"]["total"] == 0
