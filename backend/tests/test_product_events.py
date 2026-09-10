"""T-12 产品事件查询面 + 上海业务日（GWT-15.1–15.19 / 16.1–16.3）"""
from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, update

from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.product_event import ProductEvent
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant
from platform_core.models.user import User
from platform_core.tenant_context import tenant_exempt_tables, tenant_scope
from platform_core.schemas.product_event import CTA_FUNNEL


QUERY = "/api/v1/product-events"
PUBLIC = "/api/v1/public/events"


@pytest.fixture(autouse=True)
def _no_events_rate_limit(monkeypatch):
    monkeypatch.setattr(
        "backend.app.api.v1.product_events.enforce_request_limit",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "backend.app.api.v1.tenant_signup.enforce_request_limit",
        AsyncMock(return_value=None),
    )


def _query(db_client, headers, **params):
    return db_client.get(QUERY, headers=headers, params={k: v for k, v in params.items() if v is not None})


def _items(resp, name=None):
    body = resp.json()["data"]
    rows = body["items"]
    return [r for r in rows if name is None or r["event_name"] == name]


def _seed_event(db_session, **kwargs):
    async def _go():
        async with db_session() as s:
            row = ProductEvent(
                occurred_at=kwargs.get("occurred_at") or datetime(2026, 9, 1, 4, 0, 0),
                event_name=kwargs["event_name"],
                tenant_id=kwargs.get("tenant_id"),
                actor_user_id=kwargs.get("actor_user_id"),
                anonymous_id=kwargs.get("anonymous_id"),
                role=kwargs.get("role"),
                props=kwargs.get("props"),
            )
            s.add(row)
            await s.commit()
    asyncio.run(_go())


def test_gwt_15_1_task_completed_non_candidate(db_client, db_session, monkeypatch):
    from stubs import FakeRedis
    from backend.services.spider_task_service import SpiderTaskService, _SIDE_EFFECT_TASKS

    fake = FakeRedis()
    monkeypatch.setattr("backend.services.spider_task_service.get_async_redis", lambda: fake)

    async def _go():
        async with db_session() as s:
            t = Tenant(slug="co-done", name="A")
            s.add(t)
            await s.flush()
            tid = int(t.id)
            task = SpiderTask(spider_name="example", tenant_id=tid, status="running", params="{}")
            s.add(task)
            await s.commit()
            await s.refresh(task)
            await SpiderTaskService(s).finish_task(task.id, "completed", item_count=4)
            pending = [x for x in _SIDE_EFFECT_TASKS if not x.done()]
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            return tid

    tid = asyncio.run(_go())
    headers = make_platform_admin_headers(db_session)
    resp = _query(db_client, headers, event_name="task_completed")
    assert resp.status_code == 200
    row = _items(resp, "task_completed")[0]
    assert row["tenant_id"] == tid
    assert row["props"]["result_count"] == 4
    assert row["props"]["spider"] == "example"
    assert row["props"]["source"] == "collect"
    assert row["props"]["is_marketplace_candidate"] is False


def test_gwt_15_2_emit_failure_does_not_block_enqueue(db_session, monkeypatch):
    from stubs import FakeRedis, seed_worker_heartbeat
    from backend.services.spider_task_service import SpiderTaskService

    async def _tid():
        async with db_session() as s:
            t = Tenant(slug="e15-2", name="A")
            s.add(t)
            await s.flush()
            tid = int(t.id)
            await s.commit()
            return tid

    tid = asyncio.run(_tid())
    fake = FakeRedis()
    seed_worker_heartbeat(fake)
    monkeypatch.setattr("backend.services.spider_task_service.get_async_redis", lambda: fake)
    monkeypatch.setattr("backend.services.quota_service.get_async_redis", lambda: fake)

    async def _boom(*a, **k):
        raise RuntimeError("events down")

    monkeypatch.setattr("backend.services.product_event_service._persist_event", _boom)

    async def _run():
        async with db_session() as s:
            svc = SpiderTaskService(s)
            svc._ensure_spider_available = AsyncMock()
            task = await svc.enqueue("example", params="{}", tenant_id=tid)
            return task.id

    task_id = asyncio.run(_run())
    assert task_id > 0

    async def _count():
        async with db_session() as s:
            return (await s.execute(select(ProductEvent))).scalars().all()

    assert asyncio.run(_count()) == []


def test_gwt_15_3_tenant_query_is_404_shell(db_client, db_session):
    tenant_headers, _ = make_tenant_owner_headers(db_session, slug="co-15-3")
    _seed_event(db_session, event_name="login_succeeded", tenant_id=1)
    resp = _query(db_client, tenant_headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "HTTP_404"
    assert "login_succeeded" not in resp.text


def test_gwt_15_8_login_succeeded_carries_tenant(db_client, db_session):
    from backend.utils.auth import get_password_hash

    async def _seed():
        async with db_session() as s:
            t = Tenant(slug="co-login", name="A")
            s.add(t)
            await s.flush()
            s.add(User(
                username="mem-a", email="mem-a@x.com",
                password_hash=get_password_hash("SuperSecret1!"),
                role="operator", tenant_id=t.id, tenant_role="operator", is_active=True,
            ))
            await s.commit()
            return t.id

    tid = asyncio.run(_seed())
    login = db_client.post("/api/v1/auth/login", json={"username": "mem-a", "password": "SuperSecret1!"})
    assert login.status_code == 200
    headers = make_platform_admin_headers(db_session)
    rows = _items(_query(db_client, headers, event_name="login_succeeded"), "login_succeeded")
    assert any(r["tenant_id"] == tid for r in rows)
    blob = str(rows)
    assert "SuperSecret1!" not in blob
    assert "password" not in blob.lower() or "password_hash" not in blob


def test_gwt_15_4_login_failed_reasons_no_password(db_client, db_session):
    from backend.utils.auth import get_password_hash
    from backend.services.tenant_expiry_service import expire_overdue_tenants

    async def _seed():
        async with db_session() as s:
            t = Tenant(slug="co-fail", name="A", status="active")
            s.add(t)
            await s.flush()
            s.add(User(
                username="fail-a", email="fail-a@x.com",
                password_hash=get_password_hash("SuperSecret1!"),
                role="operator", tenant_id=t.id, is_active=True,
            ))
            s.add(User(
                username="locked-a", email="locked-a@x.com",
                password_hash=get_password_hash("SuperSecret1!"),
                role="operator", tenant_id=t.id, is_active=False,
            ))
            await s.commit()
            return t.id

    tid = asyncio.run(_seed())
    db_client.post("/api/v1/auth/login", json={"username": "fail-a", "password": "wrong-pass-xx"})
    db_client.post("/api/v1/auth/login", json={"username": "locked-a", "password": "SuperSecret1!"})

    async def _expire():
        async with db_session() as s:
            await s.execute(update(Tenant).where(Tenant.id == tid).values(status="expired"))
            await expire_overdue_tenants(s)
            await s.commit()

    asyncio.run(_expire())
    db_client.post("/api/v1/auth/login", json={"username": "fail-a", "password": "SuperSecret1!"})
    headers = make_platform_admin_headers(db_session)
    rows = _items(_query(db_client, headers, event_name="login_failed"), "login_failed")
    reasons = {r["props"]["reason"] for r in rows if r.get("props")}
    assert "credential" in reasons
    assert "locked" in reasons
    assert "expired" in reasons
    assert all("password" not in str(r.get("props")).lower() for r in rows)
    assert any(r["tenant_id"] == tid for r in rows)


def test_gwt_15_5_signup_keeps_browse_anonymous_id(db_client, db_session):
    db_client.post(PUBLIC, json={
        "event_name": "official_page_viewed", "anonymous_id": "anon-browse-1",
        "props": {"page": "home"},
    })
    resp = db_client.post("/api/v1/public/tenant/signup", json={
        "company": "Browse Co", "admin_email": "browse@x.com",
        "admin_password": "SuperSecret1!", "anonymous_id": "anon-browse-1",
    })
    assert resp.status_code == 200
    headers = make_platform_admin_headers(db_session)
    signups = _items(_query(db_client, headers, event_name="tenant_signup_succeeded"),
                     "tenant_signup_succeeded")
    views = _items(_query(db_client, headers, event_name="official_page_viewed"),
                   "official_page_viewed")
    assert signups[0]["anonymous_id"] == "anon-browse-1"
    assert views[0]["anonymous_id"] == "anon-browse-1"


def test_gwt_15_14_signup_without_browse_session(db_client, db_session):
    resp = db_client.post("/api/v1/public/tenant/signup", json={
        "company": "Direct Co", "admin_email": "direct@x.com",
        "admin_password": "SuperSecret1!",
    })
    assert resp.status_code == 200
    headers = make_platform_admin_headers(db_session)
    rows = _items(_query(db_client, headers, event_name="tenant_signup_succeeded"),
                  "tenant_signup_succeeded")
    assert rows
    assert rows[0]["anonymous_id"] is None


@pytest.mark.parametrize("page", ["home", "pricing", "register"])
def test_gwt_15_9_official_page_viewed(db_client, db_session, page):
    resp = db_client.post(PUBLIC, json={
        "event_name": "official_page_viewed", "anonymous_id": f"anon-{page}",
        "props": {"page": page},
    })
    assert resp.status_code == 200
    headers = make_platform_admin_headers(db_session)
    rows = _items(_query(db_client, headers, event_name="official_page_viewed"), "official_page_viewed")
    assert any(r["props"]["page"] == page for r in rows)


@pytest.mark.parametrize("cta", list(CTA_FUNNEL))
def test_gwt_15_cta_literals_not_merged(db_client, db_session, cta):
    resp = db_client.post(PUBLIC, json={
        "event_name": "official_cta_clicked", "anonymous_id": f"anon-{cta}",
        "props": {"cta": cta},
    })
    assert resp.status_code == 200
    headers = make_platform_admin_headers(db_session)
    rows = _items(_query(db_client, headers, event_name="official_cta_clicked"), "official_cta_clicked")
    hit = [r for r in rows if r["props"]["cta"] == cta]
    assert len(hit) >= 1
    others = set(CTA_FUNNEL) - {cta}
    assert hit[0]["props"]["cta"] not in others


def test_gwt_15_10_task_run_submitted(db_session, db_client, monkeypatch):
    from stubs import FakeRedis, seed_worker_heartbeat
    from backend.services.spider_task_service import SpiderTaskService

    async def _tid():
        async with db_session() as s:
            t = Tenant(slug="co-run", name="A")
            s.add(t)
            await s.flush()
            tid = int(t.id)
            await s.commit()
            return tid

    tid = asyncio.run(_tid())
    fake = FakeRedis()
    seed_worker_heartbeat(fake)
    monkeypatch.setattr("backend.services.spider_task_service.get_async_redis", lambda: fake)
    monkeypatch.setattr("backend.services.quota_service.get_async_redis", lambda: fake)

    async def _run():
        async with db_session() as s:
            svc = SpiderTaskService(s)
            svc._ensure_spider_available = AsyncMock()
            return await svc.enqueue("example", params="{}", tenant_id=tid)

    asyncio.run(_run())
    headers = make_platform_admin_headers(db_session)
    rows = _items(_query(db_client, headers, event_name="task_run_submitted"), "task_run_submitted")
    assert any(r["tenant_id"] == tid and r["props"]["spider"] == "example" for r in rows)


def test_gwt_15_11_results_exported(db_session, db_client):
    from backend.services.spider_query_service import SpiderQueryService
    from types import SimpleNamespace

    async def _tid():
        async with db_session() as s:
            t = Tenant(slug="co-exp", name="A")
            s.add(t)
            await s.flush()
            tid = int(t.id)
            await s.commit()
            return tid

    tid = asyncio.run(_tid())

    async def _emit():
        async with db_session() as s:
            svc = SpiderQueryService(s)
            await svc._emit_exported(SimpleNamespace(id=1, tenant_id=tid), "csv", 12)

    asyncio.run(_emit())
    headers = make_platform_admin_headers(db_session)
    rows = _items(_query(db_client, headers, event_name="results_exported"), "results_exported")
    assert any(r["props"]["format"] == "csv" and r["props"]["row_count"] == 12 for r in rows)


def test_gwt_15_12_quota_exceeded_dimension(db_session, db_client, monkeypatch):
    from stubs import FakeRedis
    from backend.services.quota_service import QuotaExceededException, QuotaService
    from platform_core.models.spider_task import SpiderTask

    monkeypatch.setattr("backend.services.quota_service.get_async_redis", lambda: FakeRedis())

    async def _go():
        async with db_session() as s:
            t = Tenant(slug="co-q", name="A", quota={"task_concurrency": 1})
            s.add(t)
            await s.flush()
            tid = int(t.id)
            s.add(SpiderTask(spider_name="x", tenant_id=tid, status="running", params="{}"))
            await s.commit()
            with pytest.raises(QuotaExceededException):
                await QuotaService(s).check_task_concurrency(tid)
            return tid

    tid = asyncio.run(_go())
    headers = make_platform_admin_headers(db_session)
    rows = _items(_query(db_client, headers, event_name="quota_exceeded"), "quota_exceeded")
    assert any(r["tenant_id"] == tid and r["props"]["dimension"] == "concurrency" for r in rows)


def test_gwt_15_7_enter_admin_not_in_f1(db_client, db_session):
    db_client.post(PUBLIC, json={
        "event_name": "official_cta_clicked", "anonymous_id": "anon-admin",
        "props": {"cta": "enter_admin"},
    })
    headers = make_platform_admin_headers(db_session)
    rows = _items(_query(db_client, headers, event_name="official_cta_clicked"), "official_cta_clicked")
    assert any(r["props"]["cta"] == "enter_admin" for r in rows)
    assert all(r["props"]["cta"] != "login" or r["anonymous_id"] != "anon-admin" for r in rows)
    assert "enter_admin" not in CTA_FUNNEL


def test_gwt_15_19_try_ai_flow_not_funnel_cta(db_client, db_session):
    db_client.post(PUBLIC, json={
        "event_name": "official_cta_clicked", "anonymous_id": "anon-ai",
        "props": {"cta": "try_ai_flow"},
    })
    headers = make_platform_admin_headers(db_session)
    rows = _items(_query(db_client, headers, event_name="official_cta_clicked"), "official_cta_clicked")
    assert any(r["props"]["cta"] == "try_ai_flow" for r in rows)
    assert "try_ai_flow" not in CTA_FUNNEL


def test_gwt_15_13_filter_by_tenant(db_client, db_session):
    headers = make_platform_admin_headers(db_session)
    _seed_event(db_session, event_name="login_succeeded", tenant_id=101)
    _seed_event(db_session, event_name="login_succeeded", tenant_id=202)
    only_a = _items(_query(db_client, headers, event_name="login_succeeded", tenant_id=101))
    assert {r["tenant_id"] for r in only_a} == {101}
    both = _items(_query(db_client, headers, event_name="login_succeeded"))
    assert {r["tenant_id"] for r in both} >= {101, 202}


def test_product_events_exempt_update_unfiltered(db_session):
    assert "product_events" in tenant_exempt_tables()
    async def _go():
        async with db_session() as s:
            s.add(ProductEvent(
                occurred_at=datetime(2026, 9, 1, 1, 0, 0),
                event_name="official_page_viewed", tenant_id=None,
                anonymous_id="anon-null", props={"page": "home"},
            ))
            await s.commit()
        with tenant_scope(1):
            async with db_session() as s:
                result = await s.execute(
                    update(ProductEvent).values(role="probe")
                    .execution_options(synchronize_session=False)
                )
                await s.commit()
                assert result.rowcount == 1
    asyncio.run(_go())
