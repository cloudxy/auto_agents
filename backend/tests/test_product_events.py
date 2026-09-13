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

# T-22：导入 T-35 的库/沙箱夹具（pytest 按模块命名空间解析 fixture）
from backend.tests.test_t35_asset_import import import_env  # noqa: F401


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


# ===========================================================================
# T-22（FR-92）：GWT-92.6 fail-open 逐上报点异常注入 + GWT-92.7 租户无查询面
# 七上报点 = offline_order_submitted/confirmed(T-02) · outbound_key_issued(T-05)
#          · relay_token_call_succeeded(T-09) · market_list_paged(T-14)
#          · user_restored(T-24) · asset_imported(T-35)
# ===========================================================================


@pytest.fixture
def events_channel_down(monkeypatch):
    """GWT-92.6 注入：product_events 写入通道整体故障（emit 内吞，主路径不挡）"""

    async def _boom(*_a, **_k):
        raise RuntimeError("product_events write down")

    monkeypatch.setattr("backend.services.product_event_service._persist_event", _boom)


def _t22_event_rows(db_session, *names: str) -> list:
    async def _go():
        async with db_session() as s:
            return list((await s.execute(
                select(ProductEvent).where(ProductEvent.event_name.in_(list(names)))
            )).scalars().all())

    return asyncio.run(_go())


def test_gwt_92_6_offline_order_events_fail_open(db_client, db_session, events_channel_down):
    """下单/确认收款：事件通道故障 → 申请已挂上 + 确认 paid，零事件行（GWT-92.6）"""
    from backend.tests.test_billing_orders_write_rules import _pro_plan_id, _seed_plans
    from platform_core.models.billing import Order

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="t22-926o")
    created = db_client.post(
        "/api/v1/billing/orders", headers=owner,
        json={"plan_id": _pro_plan_id(db_client), "channel": "offline"},
    )
    assert created.status_code == 201, created.text
    order_id = int(created.json()["data"]["id"])

    async def _order_state():
        async with db_session() as s:
            row = await s.get(Order, order_id)
            return row.status, row.idempotency_key

    assert asyncio.run(_order_state()) == ("pending", f"pending:{tid}")  # 申请已挂上

    pa = make_platform_admin_headers(db_session)
    confirmed = db_client.post(f"/api/v1/billing/orders/{order_id}/confirm", headers=pa)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["data"]["status"] == "paid"

    async def _paid_state():
        async with db_session() as s:
            return (await s.get(Order, order_id)).status

    assert asyncio.run(_paid_state()) == "paid"
    assert _t22_event_rows(
        db_session, "offline_order_submitted", "offline_order_confirmed",
    ) == []


def test_gwt_92_6_outbound_key_event_fail_open(db_client, db_session, events_channel_down):
    """签发钥匙：事件通道故障 → 钥匙已签发、明文可见一次（GWT-92.6）"""
    from platform_core.models.outbound_key import OutboundKey

    owner, tid = make_tenant_owner_headers(db_session, slug="t22-926k")
    resp = db_client.post("/api/v1/outbound/keys", headers=owner, json={"name": "管道"})
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["plaintext_key"].startswith("ok-")  # 明文只出现这一次

    async def _keys():
        async with db_session() as s:
            rows = (await s.execute(
                select(OutboundKey).where(OutboundKey.tenant_id == tid)
            )).scalars().all()
            return [(r.revoked_at, r.key_prefix) for r in rows]

    keys = asyncio.run(_keys())
    assert len(keys) == 1 and keys[0][0] is None  # 钥匙已落库、未吊销
    assert _t22_event_rows(db_session, "outbound_key_issued") == []


def _t22_relay_env(db_session, *, slug: str) -> tuple[int, int]:
    """一个已登记网关、未吊销、用量 0 的令牌（观察触发面成立）"""
    from platform_core.models.relay import RelayGroup, RelayToken
    from platform_core.models.tenant import Tenant

    async def _go():
        async with db_session() as s:
            t = Tenant(slug=slug, name="公司-relay")
            s.add(t)
            await s.flush()
            from platform_core.models.relay_sku_entitlement import RelaySkuEntitlement
            s.add(RelaySkuEntitlement(tenant_id=t.id, status="active"))
            g = RelayGroup(tenant_id=t.id, name="g", rpm_limit=0, tpm_limit=0)
            s.add(g)
            await s.flush()
            tok = RelayToken(
                tenant_id=t.id, group_id=g.id, name="k",
                key_prefix="sk-t22", key_hash=f"hash-{slug}", quota_tokens=-1,
                used_tokens=0, gateway_key_id=f"gwi-{slug}",
            )
            s.add(tok)
            await s.commit()
            await s.refresh(tok)
            return int(t.id), int(tok.id)

    return asyncio.run(_go())


def test_gwt_92_6_relay_usage_event_fail_open(db_session, monkeypatch, events_channel_down):
    """用量 0→≥1：事件通道故障 → 回写落库、详情/批量刷新不炸（GWT-92.6）"""
    from backend.services.relay_service import RelayService
    from platform_core.models.relay import RelayToken

    tid, token_id = _t22_relay_env(db_session, slug="t22-926r")
    monkeypatch.setattr(
        RelayService, "_observe_gateway_usage",
        AsyncMock(return_value=(7, datetime(2026, 9, 11, 4, 0, 0))),
    )

    async def _go():
        async with db_session() as s:
            out, degraded = await RelayService(s).get_token(tid, token_id)
            assert int(out.used_tokens) == 7 and degraded is False
            rows = await RelayService(s).refresh_tokens_usage(tid)
            assert [int(r.used_tokens) for r in rows] == [7]

    asyncio.run(_go())  # 不抛 = 主路径仍成功

    async def _persisted():
        async with db_session() as s:
            return int((await s.get(RelayToken, token_id)).used_tokens)

    assert asyncio.run(_persisted()) == 7  # 回写落库不回退
    assert _t22_event_rows(db_session, "relay_token_call_succeeded") == []


def test_gwt_92_6_relay_refresh_emits_with_production_expire_on_commit(
    db_engine, db_session, monkeypatch,
):
    """T-22 审查缺陷回归（红→绿）：生产 get_async_session 不带 expire_on_commit=False，
    refresh_tokens_usage 的 relay_token_call_succeeded 上报不得在吞异常圈外读
    commit 后过期属性抛 MissingGreenlet（旧实现把 fail-open 打穿成主路径失败）。"""
    from sqlalchemy.ext.asyncio import AsyncSession

    from backend.services.relay_service import RelayService

    tid, token_id = _t22_relay_env(db_session, slug="t22-926p")
    monkeypatch.setattr(
        RelayService, "_observe_gateway_usage",
        AsyncMock(return_value=(7, datetime(2026, 9, 11, 4, 0, 0))),
    )

    async def _go():
        async with AsyncSession(db_engine) as s:  # 生产形态：expire_on_commit=True
            rows = await RelayService(s).refresh_tokens_usage(tid)
            assert [int(r.used_tokens) for r in rows] == [7]
            out, degraded = await RelayService(s).get_token(tid, token_id)
            assert int(out.used_tokens) == 7 and degraded is False

    asyncio.run(_go())
    events = _t22_event_rows(db_session, "relay_token_call_succeeded")
    assert len(events) == 1  # 快照口径下事件不丢（至少一次，GWT-92.4 不回退）
    assert (events[0].props or {}).get("token_id") == token_id


def test_gwt_92_6_market_paged_event_fail_open(
    db_client, db_session, events_channel_down, monkeypatch,
):
    """公开列表翻页：事件通道故障 → 列表已翻页、页上事实不变（GWT-92.6）"""
    from backend.tests.fr33_support import fr33_asset, seed_rows

    class _RateRedis:
        async def incr(self, _key):
            return 1

        async def expire(self, _key, _ttl):
            return True

    import backend.app.api.v1.public_skills as mod

    async def _fake_redis(_key: str = "DEFAULT"):
        return _RateRedis()

    monkeypatch.setattr(mod, "get_async_redis", _fake_redis)
    seed_rows(db_session, [
        fr33_asset(name=f"t22pg-{i:02d}", title=f"夹具{i:02d}") for i in range(25)
    ])
    page2 = db_client.get("/api/v1/public/skills", params={"page": 2})
    assert page2.status_code == 200, page2.text
    data = page2.json()["data"]
    assert data["total"] == 25
    assert len(data["items"]) == 5  # 列表已翻页（25 张、页大小 20）
    assert data["has_more"] is False
    assert _t22_event_rows(db_session, "market_list_paged") == []


def test_gwt_92_6_user_restored_event_fail_open(db_client, db_session, events_channel_down):
    """恢复软删用户：事件通道故障 → 恢复成功、用户回在册（GWT-92.6/92.8）"""
    from platform_core.models.tenant import Tenant
    from platform_core.models.user import User

    async def _seed():
        async with db_session() as s:
            t = Tenant(slug="t22-926u", name="公司-恢复")
            s.add(t)
            await s.flush()
            gone = User(
                username="gone-t22", email="gone-t22@x.co", password_hash="x",
                role="viewer", tenant_id=t.id, tenant_role="viewer",
                deleted_at=datetime(2026, 9, 10, 0, 0, 0), is_active=False,
            )
            s.add(gone)
            await s.commit()
            await s.refresh(gone)
            return int(gone.id)

    uid = asyncio.run(_seed())
    pa = make_platform_admin_headers(db_session)
    resp = db_client.post(f"/api/v1/admin/users/{uid}/restore", headers=pa)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["deleted_at"] is None

    async def _alive():
        async with db_session() as s:
            row = await s.get(User, uid)
            return row.deleted_at is None and row.is_active is True

    assert asyncio.run(_alive())
    assert _t22_event_rows(db_session, "user_restored") == []


def test_gwt_92_6_asset_imported_event_fail_open(db_client, db_session, import_env, events_channel_down):
    """资产导入：事件通道故障 → 导入完成、资产已落库（GWT-92.6/92.9）"""
    from backend.tests.test_t35_asset_import import SKILL_MD, _post_zip, _zip
    from platform_core.models.capability import CapabilityAsset

    pa = make_platform_admin_headers(db_session)
    resp = _post_zip(db_client, pa, _zip({"imported-skill/SKILL.md": SKILL_MD}))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["succeeded"] == 1 and data["status"] == "completed"

    async def _assets():
        async with db_session() as s:
            rows = (await s.execute(
                select(CapabilityAsset).where(CapabilityAsset.name == "imported-skill")
            )).scalars().all()
            return [(r.listing_state, r.asset_type) for r in rows]

    assert asyncio.run(_assets()) == [("unlisted", "skill")]  # 资产已落库
    assert (import_env["library"] / "skills" / "imported-skill" / "SKILL.md").exists()
    assert _t22_event_rows(db_session, "asset_imported") == []


def test_gwt_92_7_tenant_query_face_same_shape_as_missing_page(db_client, db_session):
    """租户直打查询面 = 与「页面不存在」同形（v2 仍真）：统一 404 信封、非 403、零泄露"""
    tenant_headers, _tid = make_tenant_owner_headers(db_session, slug="t22-927")
    _seed_event(db_session, event_name="offline_order_confirmed", tenant_id=1)
    faced = db_client.get(QUERY, headers=tenant_headers)
    # 同形对照：租户直打另一个「对其不存在」的平台页（同走 require_platform_admin_or_404）
    other_missing = db_client.get("/api/v1/admin/tenants", headers=tenant_headers)
    assert faced.status_code == other_missing.status_code == 404
    fb, ob = faced.json(), other_missing.json()
    assert set(fb) == set(ob)  # 同形：同一信封键集
    for key in ("success", "code", "message", "data"):
        assert fb[key] == ob[key]
    assert fb["code"] == "HTTP_404" and fb["message"] == "Not Found"  # 不是 403 信封
    assert "FORBIDDEN" not in faced.text and "403" not in fb["code"]
    assert "offline_order_confirmed" not in faced.text  # 零事实泄露
