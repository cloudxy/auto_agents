"""T-01 夹具名单 + 产品事件 is_internal_fixture 快照（FR-U03 / FR-U01）。"""
from __future__ import annotations

import asyncio
from datetime import datetime

from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.product_event import ProductEvent
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant
from platform_core.tenant_context import tenant_exempt_tables, tenant_scope
from sqlalchemy import select, update

QUERY = "/api/v1/product-events"
FIXTURES = "/api/v1/admin/internal-fixture-tenants"


def _items(resp, name=None):
    rows = resp.json()["data"]["items"]
    return [r for r in rows if name is None or r["event_name"] == name]


def _query(db_client, headers, **params):
    return db_client.get(
        QUERY, headers=headers, params={k: v for k, v in params.items() if v is not None},
    )


def _complete_example(db_session, monkeypatch, *, slug: str, item_count: int = 3) -> int:
    from stubs import FakeRedis
    from backend.services.spider_task_service import SpiderTaskService, _SIDE_EFFECT_TASKS

    fake = FakeRedis()
    monkeypatch.setattr("backend.services.spider_task_service.get_async_redis", lambda: fake)

    async def _go():
        async with db_session() as s:
            t = Tenant(slug=slug, name=slug)
            s.add(t)
            await s.flush()
            tid = int(t.id)
            task = SpiderTask(spider_name="example", tenant_id=tid, status="running", params="{}")
            s.add(task)
            await s.commit()
            await s.refresh(task)
            await SpiderTaskService(s).finish_task(task.id, "completed", item_count=item_count)
            pending = [x for x in _SIDE_EFFECT_TASKS if not x.done()]
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            return tid

    return asyncio.run(_go())


def _seed_event(db_session, **kwargs):
    async def _go():
        async with db_session() as s:
            s.add(ProductEvent(
                occurred_at=kwargs.get("occurred_at") or datetime(2026, 9, 12, 4, 0, 0),
                event_name=kwargs["event_name"],
                tenant_id=kwargs.get("tenant_id"),
                props=kwargs.get("props"),
                is_internal_fixture=kwargs.get("is_internal_fixture", None),
            ))
            await s.commit()
    asyncio.run(_go())


def test_gwt_u03_1_non_fixture_completed_snapshot_false(db_client, db_session, monkeypatch):
    tid = _complete_example(db_session, monkeypatch, slug="co-u03-1")
    headers = make_platform_admin_headers(db_session)
    resp = _query(db_client, headers, event_name="task_completed", tenant_id=tid)
    assert resp.status_code == 200
    row = _items(resp, "task_completed")[0]
    assert row["tenant_id"] == tid
    assert row["props"]["result_count"] == 3
    assert row["props"]["is_marketplace_candidate"] is False
    assert row["is_internal_fixture"] is False


def test_gwt_u03_2_fixture_excluded_from_north_star(db_client, db_session, monkeypatch):
    async def _tenant():
        async with db_session() as s:
            t = Tenant(slug="co-u03-2", name="fixture-co")
            s.add(t)
            await s.flush()
            await s.commit()
            return int(t.id)

    tid = asyncio.run(_tenant())
    headers = make_platform_admin_headers(db_session)
    added = db_client.post(FIXTURES, headers=headers, json={"tenant_id": tid})
    assert added.status_code in (200, 201)
    assert added.json()["data"]["tenant_id"] == tid

    from stubs import FakeRedis
    from backend.services.spider_task_service import SpiderTaskService, _SIDE_EFFECT_TASKS

    fake = FakeRedis()
    monkeypatch.setattr("backend.services.spider_task_service.get_async_redis", lambda: fake)

    async def _finish():
        async with db_session() as s:
            task = SpiderTask(spider_name="example", tenant_id=tid, status="running", params="{}")
            s.add(task)
            await s.commit()
            await s.refresh(task)
            await SpiderTaskService(s).finish_task(task.id, "completed", item_count=2)
            pending = [x for x in _SIDE_EFFECT_TASKS if not x.done()]
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    asyncio.run(_finish())
    north = _items(_query(
        db_client, headers, event_name="task_completed", is_internal_fixture=False, tenant_id=tid,
    ))
    assert north == []
    raw = _items(_query(db_client, headers, event_name="task_completed", tenant_id=tid))
    assert raw[0]["is_internal_fixture"] is True
    flagged = _items(_query(
        db_client, headers, event_name="task_completed", is_internal_fixture=True, tenant_id=tid,
    ))
    assert flagged[0]["is_internal_fixture"] is True


def test_gwt_u03_3_tenant_query_and_membership_are_404(db_client, db_session):
    tenant_headers, _ = make_tenant_owner_headers(db_session, slug="co-u03-3")
    _seed_event(db_session, event_name="task_completed", tenant_id=1, is_internal_fixture=False)
    q = _query(db_client, tenant_headers)
    assert q.status_code == 404
    assert q.json()["code"] == "HTTP_404"
    listed = db_client.get(FIXTURES, headers=tenant_headers)
    assert listed.status_code == 404
    assert listed.json()["code"] == "HTTP_404"
    added = db_client.post(FIXTURES, headers=tenant_headers, json={"tenant_id": 1})
    assert added.status_code == 404
    assert "task_completed" not in q.text


def test_gwt_u03_4_blocked_distinct_from_completed(db_client, db_session):
    headers = make_platform_admin_headers(db_session)

    async def _emit():
        from backend.services.product_event_service import emit_product_event
        async with db_session() as s:
            t = Tenant(slug="co-u03-4", name="blocked")
            s.add(t)
            await s.flush()
            tid = int(t.id)
            await s.commit()
            await emit_product_event(
                s, "task_blocked", tenant_id=tid,
                props={"reason": "worker_offline", "spider": "example"},
            )
            return tid

    tid = asyncio.run(_emit())
    blocked = _items(_query(db_client, headers, event_name="task_blocked", tenant_id=tid))
    done = _items(_query(db_client, headers, event_name="task_completed", tenant_id=tid))
    assert len(blocked) == 1
    assert blocked[0]["props"]["reason"] == "worker_offline"
    assert blocked[0]["is_internal_fixture"] is False
    assert not any((r.get("props") or {}).get("result_count", 0) > 0 for r in done)


def test_gwt_u03_5_completed_not_in_blocked_numerator(db_client, db_session, monkeypatch):
    tid = _complete_example(db_session, monkeypatch, slug="co-u03-5")
    headers = make_platform_admin_headers(db_session)
    blocked = _items(_query(db_client, headers, event_name="task_blocked", tenant_id=tid))
    done = _items(_query(db_client, headers, event_name="task_completed", tenant_id=tid))
    assert blocked == []
    assert done[0]["props"]["result_count"] > 0
    assert done[0]["is_internal_fixture"] is False


def test_snapshot_unchanged_after_membership_remove(db_client, db_session, monkeypatch):
    async def _tenant():
        async with db_session() as s:
            t = Tenant(slug="co-u03-snap", name="snap")
            s.add(t)
            await s.flush()
            await s.commit()
            return int(t.id)

    tid = asyncio.run(_tenant())
    headers = make_platform_admin_headers(db_session)
    assert db_client.post(FIXTURES, headers=headers, json={"tenant_id": tid}).status_code in (200, 201)

    from stubs import FakeRedis
    from backend.services.spider_task_service import SpiderTaskService, _SIDE_EFFECT_TASKS

    fake = FakeRedis()
    monkeypatch.setattr("backend.services.spider_task_service.get_async_redis", lambda: fake)

    async def _finish():
        async with db_session() as s:
            task = SpiderTask(spider_name="example", tenant_id=tid, status="running", params="{}")
            s.add(task)
            await s.commit()
            await s.refresh(task)
            await SpiderTaskService(s).finish_task(task.id, "completed", item_count=1)
            pending = [x for x in _SIDE_EFFECT_TASKS if not x.done()]
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    asyncio.run(_finish())
    removed = db_client.delete(f"{FIXTURES}/{tid}", headers=headers)
    assert removed.status_code == 200
    north = _items(_query(
        db_client, headers, event_name="task_completed", is_internal_fixture=False, tenant_id=tid,
    ))
    assert north == []
    raw = _items(_query(db_client, headers, event_name="task_completed", tenant_id=tid))
    assert raw[0]["is_internal_fixture"] is True


def test_null_legacy_events_excluded_from_non_fixture_filter(db_client, db_session):
    headers = make_platform_admin_headers(db_session)
    _seed_event(db_session, event_name="task_completed", tenant_id=77, is_internal_fixture=None,
                props={"result_count": 1, "is_marketplace_candidate": False})
    north = _items(_query(
        db_client, headers, event_name="task_completed", is_internal_fixture=False, tenant_id=77,
    ))
    assert north == []
    raw = _items(_query(db_client, headers, event_name="task_completed", tenant_id=77))
    assert raw[0]["is_internal_fixture"] is None


def test_add_fixture_is_idempotent_unique_tenant(db_client, db_session):
    async def _tenant():
        async with db_session() as s:
            t = Tenant(slug="co-u03-uk", name="uk")
            s.add(t)
            await s.flush()
            await s.commit()
            return int(t.id)

    tid = asyncio.run(_tenant())
    headers = make_platform_admin_headers(db_session)
    first = db_client.post(FIXTURES, headers=headers, json={"tenant_id": tid})
    second = db_client.post(FIXTURES, headers=headers, json={"tenant_id": tid})
    assert first.status_code in (200, 201)
    assert second.status_code in (200, 201)
    listed = db_client.get(FIXTURES, headers=headers)
    assert listed.status_code == 200
    rows = [r for r in listed.json()["data"]["items"] if r["tenant_id"] == tid]
    assert len(rows) == 1


def test_internal_fixture_tenants_exempt_update_unfiltered(db_session):
    from platform_core.models.internal_fixture_tenant import InternalFixtureTenant

    assert "internal_fixture_tenants" in tenant_exempt_tables()

    async def _go():
        async with db_session() as s:
            s.add(InternalFixtureTenant(tenant_id=9, created_by="root"))
            await s.commit()
        with tenant_scope(1):
            async with db_session() as s:
                result = await s.execute(
                    update(InternalFixtureTenant).values(created_by="probe")
                    .execution_options(synchronize_session=False)
                )
                await s.commit()
                assert result.rowcount == 1
                row = (await s.execute(select(InternalFixtureTenant))).scalar_one()
                assert row.created_by == "probe"

    asyncio.run(_go())
