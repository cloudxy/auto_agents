"""T-08 / FR-M12：按商品码履约；专业档三数字；enterprise 写 SKU；relay 不改配额。"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from backend.services.quota_service import PLAN_FULL_USER, TASK_QUOTA_LIMIT_CODE
from backend.tests.payment_notify_support import sku_status, tenant_quota
from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.billing import Plan
from platform_core.models.llm_token_usage import LlmTokenUsage
from platform_core.models.spider_result import SpiderResult
from platform_core.models.spider_task import SpiderTask
from test_llm_four_actions_http import (
    PLAN_JSON, _get_plan, _install_llm_seams, _wire_plan,
)

CHECKOUT = "/api/v1/billing/checkout"
CONFIRM = "/api/v1/billing/orders/{id}/confirm"
RUN = "/api/v1/spiders/run"
PLANS = "/api/v1/ai/plans"
ENQUEUED = "已入队"
PRO = {"task_concurrency": 50, "result_storage": 200000, "llm_tokens_month": 5000000}
ENT = {"task_concurrency": 50, "result_storage": 2000000, "llm_tokens_month": 20000000}


def _seed(db_session) -> None:
    async def _go():
        async with db_session() as s:
            if (await s.execute(select(Plan).where(Plan.slug == "pro"))).scalar_one_or_none():
                return
            s.add_all([
                Plan(
                    slug="pro", name="专业档", price_cents=29900, period="month",
                    quota_json='{"task_concurrency":20,"result_storage":500000,"llm_tokens_month":5000000}',
                    is_public=1,
                ),
                Plan(
                    slug="enterprise", name="企业档", price_cents=99900, period="month",
                    quota_json='{"task_concurrency":50,"result_storage":2000000,"llm_tokens_month":20000000}',
                    is_public=1,
                ),
            ])
            await s.commit()

    asyncio.run(_go())


def _confirm(db_client, db_session, slug: str, product: str, monkeypatch=None):
    if product == "relay" and monkeypatch is not None:
        import backend.services.billing_service as billing_mod
        orig = billing_mod.settings.get

        def _get(key, default=None):
            if key == "BILLING.RELAY_PRICE_CENTS":
                return 19900
            return orig(key, default)

        monkeypatch.setattr(billing_mod.settings, "get", _get)
    _seed(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug=slug)
    pa = make_platform_admin_headers(db_session)
    before = tenant_quota(db_session, tid)
    created = db_client.post(CHECKOUT, headers=owner, json={"product": product})
    assert created.status_code == 201, created.text
    oid = created.json()["data"]["id"]
    resp = db_client.post(CONFIRM.format(id=oid), headers=pa)
    assert resp.status_code == 200, resp.text
    return tid, resp.json()["data"], before, owner


def _seed_worker(monkeypatch):
    from stubs import FakeRedis, seed_worker_heartbeat

    fake = FakeRedis()
    seed_worker_heartbeat(fake)
    import backend.services.quota_service as quota_mod
    import backend.services.spider_task_service as svc_mod

    monkeypatch.setattr(svc_mod, "get_async_redis", lambda: fake)
    monkeypatch.setattr(quota_mod, "get_async_redis", lambda: fake)
    return fake


def _seed_running(db_session, tid: int, n: int) -> None:
    async def _go():
        async with db_session() as s:
            s.add_all([
                SpiderTask(
                    spider_name="example", tenant_id=tid, status="running", params="{}",
                )
                for _ in range(n)
            ])
            await s.commit()

    asyncio.run(_go())


def _seed_owned_results(db_session, tid: int, n: int) -> None:
    async def _go():
        async with db_session() as s:
            task = SpiderTask(
                spider_name="example", tenant_id=tid, status="completed", params="{}",
            )
            s.add(task)
            await s.flush()
            tid_task = int(task.id)
            s.add_all([
                SpiderResult(
                    task_id=tid_task, tenant_id=tid, spider_name="example",
                    url=f"https://m12.example/{i}", title=str(i), source="web",
                )
                for i in range(n)
            ])
            await s.commit()

    asyncio.run(_go())


def _seed_month_tokens(db_session, tid: int, total: int) -> None:
    from backend.services.quota_service import shanghai_today

    async def _go():
        async with db_session() as s:
            s.add(LlmTokenUsage(
                tenant_id=tid, provider_name="config", model="m",
                stat_date=shanghai_today(), total_tokens=total,
            ))
            await s.commit()

    asyncio.run(_go())


def test_gwt_m12_6_pro_enforcement_not_seed_20(db_client, db_session):
    """专业档履约写定价页 50/200000/5M，不是 040 种子 20/500k。"""
    tid, data, _before, _owner = _confirm(db_client, db_session, "m12-6", "plan_pro")
    assert data["status"] == "fulfilled"
    q = tenant_quota(db_session, tid)
    assert q["task_concurrency"] == 50
    assert q["result_storage"] == 200000
    assert q["llm_tokens_month"] == 5000000
    assert sku_status(db_session, tid) == "none"


def test_gwt_m12_6_sixth_task_enqueues_after_five_running(
    db_client, db_session, monkeypatch,
):
    """GWT-M12.6：专业档开通后 5 个 running 再 POST /spiders/run → 已入队（不是免费 5 帽）。"""
    _seed_worker(monkeypatch)
    tid, data, _before, owner = _confirm(db_client, db_session, "m12-6run", "plan_pro")
    assert data["status"] == "fulfilled"
    _seed_running(db_session, tid, 5)
    resp = db_client.post(
        RUN, headers=owner,
        json={"spider_name": "example", "params": "{\"urls\":[\"https://httpbin.org/get\"]}"},
    )
    assert resp.status_code == 200, resp.text
    assert ENQUEUED in resp.json()["message"]
    assert resp.json()["code"] != "QUOTA_EXCEEDED"


def test_gwt_m12_7_storage_10001_still_enqueues(db_client, db_session, monkeypatch):
    """GWT-M12.7：专业档开通后已有 10001 条结果再采集 → 已入队（不是免费 10000 帽）。"""
    _seed_worker(monkeypatch)
    tid, data, _before, owner = _confirm(db_client, db_session, "m12-7", "plan_pro")
    assert data["status"] == "fulfilled"
    _seed_owned_results(db_session, tid, 10001)
    resp = db_client.post(
        RUN, headers=owner,
        json={"spider_name": "example", "params": "{\"urls\":[\"https://httpbin.org/get\"]}"},
    )
    assert resp.status_code == 200, resp.text
    assert ENQUEUED in resp.json()["message"]
    assert resp.json()["code"] != "QUOTA_EXCEEDED"


def test_gwt_m12_4_pro_does_not_activate_relay(db_client, db_session):
    tid, _data, _before, _owner = _confirm(db_client, db_session, "m12-4", "plan_pro")
    assert sku_status(db_session, tid) == "none"


def test_gwt_m11_15_enterprise_writes_quota_and_sku(db_client, db_session):
    tid, data, _before, _owner = _confirm(db_client, db_session, "m11-15", "plan_enterprise")
    assert data["status"] == "fulfilled"
    q = tenant_quota(db_session, tid)
    assert q == ENT
    assert q != PRO
    assert sku_status(db_session, tid) == "active"


def test_gwt_m11_17_relay_sku_keeps_free_quota(db_client, db_session, monkeypatch):
    tid, data, before, _owner = _confirm(db_client, db_session, "m11-17", "relay", monkeypatch)
    assert data["status"] == "fulfilled"
    assert sku_status(db_session, tid) == "active"
    assert tenant_quota(db_session, tid) == before


def _open_planning_gateway(monkeypatch, db_engine, db_session) -> list[str]:
    """GWT-70.1：无本企业激活供应商、网关可达、至少一条模型。"""
    from config import settings

    settings.set("LLM.DATA_PLANE", "litellm")
    settings.set("LITELLM.BASE_URL", "http://gw.test")
    settings.set("LITELLM.MASTER_KEY", "sk-virt")
    settings.set("LLM.MAX_RETRIES", 1)
    settings.set("LLM.ENABLED", True)
    _install_llm_seams(monkeypatch)
    outbound: list[str] = []
    _wire_plan(monkeypatch, db_engine, db_session, "ok", outbound, PLAN_JSON)
    return outbound


def _post_plan_then_launch(db_client, headers):
    created = db_client.post(
        PLANS, headers=headers,
        json={
            "target_url": "https://example.com/list",
            "html_snippet": "<html><h1>t</h1></html>",
        },
    )
    assert created.status_code in (200, 201), created.text
    pid = int(created.json()["data"]["id"])
    launched = db_client.post(f"{PLANS}/{pid}/plan", headers=headers)
    return pid, launched


def test_gwt_m12_8_tokens_200001_plan_visible_not_free_cap(
    db_client, db_engine, db_session, monkeypatch,
):
    """GWT-M12.8：专业档开通 + 200001 token + GWT-70.1 网关 → 规划 200、可见方案，不是免费 20 万句。"""
    outbound = _open_planning_gateway(monkeypatch, db_engine, db_session)
    tid, data, _before, owner = _confirm(db_client, db_session, "m12-8", "plan_pro")
    assert data["status"] == "fulfilled"
    assert tenant_quota(db_session, tid)["llm_tokens_month"] == 5000000
    _seed_month_tokens(db_session, tid, 200001)
    pid, launched = _post_plan_then_launch(db_client, owner)
    assert launched.status_code == 200, launched.text
    body = launched.json()
    assert body.get("code") != TASK_QUOTA_LIMIT_CODE
    assert PLAN_FULL_USER not in launched.text
    snap = body.get("data") or {}
    flow = (snap.get("plan_json") or {}).get("flow") or snap.get("plan_json") or {}
    selectors = flow.get("selectors") or (snap.get("generated_params") or {}).get("selectors")
    assert selectors, snap
    assert snap.get("status") != "failed"
    detail = _get_plan(db_client, owner, pid)
    assert detail.get("plan_json") or detail.get("generated_params")
    assert outbound, "GWT-70.1：规划必须打到网关"


def test_gwt_m12_8_free_tier_200001_blocks_plan(
    db_client, db_engine, db_session, monkeypatch,
):
    """对照：未开通专业档、用量 200001 → 规划被免费 20 万拦住（证明 Then 非空心）。"""
    _open_planning_gateway(monkeypatch, db_engine, db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="m12-8free")
    _seed_month_tokens(db_session, tid, 200001)
    _pid, launched = _post_plan_then_launch(db_client, owner)
    assert launched.json()["code"] == TASK_QUOTA_LIMIT_CODE
    assert PLAN_FULL_USER in launched.json()["message"]
    assert launched.status_code != 200
