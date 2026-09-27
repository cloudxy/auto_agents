"""S3-1 配额契约与检查点验证（工单 39）

Seam（工单预确认）：QuotaService 三检查点 + 超限业务码（db_session 直测）。
"""
from datetime import date

import pytest

from backend.services.quota_service import (
    DEFAULT_QUOTA, QuotaExceededException, QuotaService, quota_of,
)
from platform_core.models.llm_token_usage import LlmTokenUsage
from platform_core.models.spider_result import SpiderResult
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant


_SEQ = 0


async def _tenant(db_session, **quota) -> int:
    global _SEQ
    _SEQ += 1
    async with db_session() as s:
        t = Tenant(slug=f"q-{_SEQ}", name="Q", quota=quota or None)
        s.add(t)
        await s.commit()
        async with db_session() as s2:
            return (await s2.execute(
                __import__("sqlalchemy").select(Tenant).where(Tenant.slug == f"q-{_SEQ}")
            )).scalar_one().id


@pytest.mark.asyncio
async def test_default_quota_merge(db_session):
    """行级 quota 与平台默认逐键合并（部分覆盖生效）"""
    async with db_session() as s:
        t = Tenant(slug="q-merge", name="Q", quota={"task_concurrency": 99})
        s.add(t)
        await s.flush()
        merged = quota_of(t)
    assert merged["task_concurrency"] == 99
    assert merged["result_storage"] == DEFAULT_QUOTA["result_storage"]


@pytest.mark.asyncio
async def test_task_concurrency_over_limit_rejected(db_session):
    tid = await _tenant(db_session, task_concurrency=2)
    async with db_session() as s:
        s.add_all([
            SpiderTask(spider_name="t1", tenant_id=tid, status="running", params="{}"),
            SpiderTask(spider_name="t2", tenant_id=tid, status="pending", params="{}"),
        ])
        await s.commit()
    async with db_session() as s:
        with pytest.raises(QuotaExceededException, match="任务并发"):
            await QuotaService(s).check_task_concurrency(tid)


@pytest.mark.asyncio
async def test_result_storage_over_limit_rejected(db_session):
    tid = await _tenant(db_session, result_storage=1)
    async with db_session() as s:
        s.add(SpiderResult(task_id=1, spider_name="x", url="https://u", tenant_id=tid))
        await s.commit()
    async with db_session() as s:
        with pytest.raises(QuotaExceededException, match="结果存储"):
            await QuotaService(s).check_result_storage(tid)


@pytest.mark.asyncio
async def test_llm_tokens_month_over_limit_rejected(db_session):
    tid = await _tenant(db_session, llm_tokens_month=100)
    async with db_session() as s:
        s.add(LlmTokenUsage(
            tenant_id=tid, provider_name="provider:1", model="m",
            stat_date=date(2026, 9, 1), total_tokens=150,
        ))
        await s.commit()
    async with db_session() as s:
        with pytest.raises(QuotaExceededException, match="LLM token"):
            await QuotaService(s).check_llm_tokens_month(tid, "2026-09")


@pytest.mark.asyncio
async def test_usage_overview_shape(db_session):
    tid = await _tenant(db_session)
    async with db_session() as s:
        s.add_all([
            SpiderTask(spider_name="a", tenant_id=tid, status="running", params="{}"),
            LlmTokenUsage(tenant_id=tid, provider_name="provider:1", model="m",
                          stat_date=date(2026, 9, 1), total_tokens=50, cost_cents=120),
            LlmTokenUsage(tenant_id=tid, provider_name="provider:2", model="m",
                          stat_date=date(2026, 9, 2), total_tokens=30, cost_cents=30),
        ])
        await s.commit()
    async with db_session() as s:
        overview = await QuotaService(s).usage_overview(tid, "2026-09")
    assert overview["usage"]["task_concurrency"] == 1
    assert overview["usage"]["llm_tokens_month"] == 80
    assert overview["llm_by_provider"] == {"provider:1": 50, "provider:2": 30}
    assert overview["cost_by_provider"] == {"provider:1": 120, "provider:2": 30}
    assert overview["cost_cents_total"] == 150
    assert overview["quota"]["task_concurrency"] == DEFAULT_QUOTA["task_concurrency"]


def test_quota_exception_is_429():

    exc = QuotaExceededException("x")
    assert exc.status_code == 429
    assert exc.code == "QUOTA_EXCEEDED"


@pytest.mark.asyncio
async def test_usage_overview_near_limit_alert_has_no_internal_code(db_session):
    """GWT-12.2：≥90% 未满 → 接近上限句，不含内部码。"""
    from backend.services.quota_service import NEAR_LIMIT_USER, PLAN_FULL_USER

    tid = await _tenant(db_session, llm_tokens_month=100)
    async with db_session() as s:
        s.add(LlmTokenUsage(
            tenant_id=tid, provider_name="provider:1", model="m",
            stat_date=date(2026, 9, 1), total_tokens=90,
        ))
        await s.commit()
    async with db_session() as s:
        overview = await QuotaService(s).usage_overview(tid, "2026-09")
    near = [a for a in overview["alerts"] if a["level"] == "near"]
    assert near and near[0]["message"] == NEAR_LIMIT_USER
    blob = str(overview)
    assert "QUOTA_EXCEEDED" not in blob
    assert "429" not in blob
    assert PLAN_FULL_USER not in [a["message"] for a in overview["alerts"]]


@pytest.mark.asyncio
async def test_usage_overview_full_alert_is_plan_full_sentence(db_session):
    """GWT-12.3 用量侧：满额告警句是已达配额上限，不含内部码。"""
    from backend.services.quota_service import PLAN_FULL_USER

    tid = await _tenant(db_session, llm_tokens_month=100)
    async with db_session() as s:
        s.add(LlmTokenUsage(
            tenant_id=tid, provider_name="provider:1", model="m",
            stat_date=date(2026, 9, 1), total_tokens=100,
        ))
        await s.commit()
    async with db_session() as s:
        overview = await QuotaService(s).usage_overview(tid, "2026-09")
    full = [a for a in overview["alerts"] if a["level"] == "full"]
    assert full and full[0]["message"] == PLAN_FULL_USER
    assert "QUOTA_EXCEEDED" not in str(overview)


def _enable_cfg():
    from backend.services.llm_common import LlmRuntimeConfig

    return LlmRuntimeConfig(
        base_url="https://pub", api_key="sk-pub", model="m",
        temperature=0.2, timeout=5, max_retries=1, enabled=True,
        source="provider:platform", provider_id=None, protocol="openai_compatible",
    )


class _RecordingClient:
    def __init__(self, bucket: list, *a, **k):
        self.bucket = bucket

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        self.bucket.append({"url": url, "json": json})

        class _Resp:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"total_tokens": 1, "prompt_tokens": 1, "completion_tokens": 0},
                }

        return _Resp()


@pytest.mark.asyncio
async def test_llm_chat_under_quota_not_rejected_by_plan_gate(db_session, monkeypatch):
    """GWT-12.1：月度 token 未尽，规划/对话不被套餐闸拒绝。"""
    import backend.services.ai_planner_service as aps
    import backend.services.ai_planner.llm_client as lc

    tid = await _tenant(db_session, llm_tokens_month=1000)
    async with db_session() as s:
        s.add(LlmTokenUsage(
            tenant_id=tid, provider_name="provider:1", model="m",
            stat_date=date(2026, 9, 1), total_tokens=10,
        ))
        await s.commit()

    outbound: list = []

    async def _resolve():
        return _enable_cfg()

    async def _month(dim, **kw):
        return 0

    monkeypatch.setattr(
        "backend.services.ai_planner_service._resolve_llm_runtime_config", _resolve,
    )
    monkeypatch.setattr(aps, "quota_session_factory", db_session, raising=False)
    monkeypatch.setattr(lc, "get_month_used", _month)
    monkeypatch.setattr(
        lc.httpx, "AsyncClient", lambda *a, **k: _RecordingClient(outbound, *a, **k),
    )

    from platform_core.tenant_context import tenant_scope

    with tenant_scope(tid):
        content = await lc.llm_chat([{"role": "user", "content": "hi"}])
    assert content == "ok"
    assert outbound and outbound[0]["url"].startswith("https://pub")


@pytest.mark.asyncio
async def test_platform_cost_fuse_copy_is_not_plan_full(db_session, monkeypatch):
    """GWT-12.5：套餐未尽但平台成本熔断，文案不是套餐超限句；不出站。"""
    import backend.services.ai_planner_service as aps
    import backend.services.ai_planner.llm_client as lc
    from backend.services.quota_service import PLAN_FULL_CTA, PLAN_FULL_USER
    from platform_core.exceptions import BusinessException
    from platform_core.tenant_context import tenant_scope

    tid = await _tenant(db_session, llm_tokens_month=100000)
    outbound: list = []

    async def _resolve():
        return _enable_cfg()

    async def _month(dim, **kw):
        return 100

    monkeypatch.setattr(
        "backend.services.ai_planner_service._resolve_llm_runtime_config", _resolve,
    )
    monkeypatch.setattr(aps, "quota_session_factory", db_session, raising=False)
    monkeypatch.setattr(lc, "get_month_used", _month)
    monkeypatch.setattr(
        lc.httpx, "AsyncClient", lambda *a, **k: _RecordingClient(outbound, *a, **k),
    )

    with tenant_scope(tid):
        with pytest.raises(BusinessException) as ei:
            await lc.llm_chat(
                [{"role": "user", "content": "hi"}], budget_override=100,
            )
    assert ei.value.code == "LLM_COST_FUSE"
    assert PLAN_FULL_USER not in ei.value.message
    assert PLAN_FULL_CTA not in ei.value.message
    assert "QUOTA_EXCEEDED" not in ei.value.message
    assert outbound == []


def test_gwt_16_3_platform_admin_usage_belongs_to_tenant_space(platform_admin_client):
    resp = platform_admin_client.get("/api/v1/tenants/me/usage")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["message"] == "用量属于企业空间"
    assert "暂无用量数据" not in str(data)


def test_readonly_usage_cannot_change_plan_and_cannot_render_gateway_failure_as_quota(
    db_client, db_session,
):
    """GWT-12.4 与 GWT-74.3 并格：只读打开用量只读可见进度；不能改套餐；
    不能把网关失败写成套餐已满。同一写权、同一夹具。"""
    import asyncio
    import json

    from backend.services.auth_service import AuthService
    from backend.services.quota_service import (
        PLAN_FULL_CTA,
        PLAN_FULL_USER,
        build_usage_alerts,
        shanghai_year_month,
        user_visible_llm_failure,
    )
    from platform_core.models.user import User

    state: dict = {}
    ym = shanghai_year_month()
    stat = date(int(ym[:4]), int(ym[5:7]), 1)

    async def _seed():
        async with db_session() as s:
            t = Tenant(slug="ro-usage", name="RO", quota={"llm_tokens_month": 100})
            s.add(t)
            await s.flush()
            viewer = User(
                username="ro-viewer", email="ro@x.local", password_hash="x",
                role="viewer", tenant_id=t.id, tenant_role="viewer",
            )
            s.add(viewer)
            s.add(LlmTokenUsage(
                tenant_id=t.id, provider_name="provider:1", model="m",
                stat_date=stat, total_tokens=40,
            ))
            await s.commit()
            token = await AuthService(s).create_token({
                "id": viewer.id, "username": viewer.username, "is_admin": False,
                "role": "viewer", "tenant_id": t.id, "tenant_role": "viewer",
                "is_platform_admin": False,
            })
            state["token"] = token.access_token
            state["tenant"] = t.id

    asyncio.run(_seed())
    headers = {"Authorization": f"Bearer {state['token']}"}

    resp = db_client.get("/api/v1/tenants/me/usage", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["usage"]["llm_tokens_month"] == 40
    assert data["quota"]["llm_tokens_month"] == 100
    blob = json.dumps(data, ensure_ascii=False)
    assert "QUOTA_EXCEEDED" not in blob
    assert PLAN_FULL_USER not in blob

    plan = db_client.patch("/api/v1/tenants/me/quota", headers=headers, json={"llm_tokens_month": 999999})
    assert plan.status_code == 403
    admin_plan = db_client.patch(
        f"/api/v1/admin/tenants/{state['tenant']}",
        headers=headers, json={"quota": {"llm_tokens_month": 999999}},
    )
    assert admin_plan.status_code == 404  # 平台写面直打 404 同形；只读仍改不了套餐

    gw = user_visible_llm_failure("LLM_GATEWAY_UNREACHABLE", "connection refused")
    assert gw == "平台 LLM 网关不可达"
    assert PLAN_FULL_USER not in gw
    assert PLAN_FULL_CTA not in gw
    assert "QUOTA_EXCEEDED" not in gw
    mixed = build_usage_alerts(data["usage"], data["quota"], llm_error_code="LLM_GATEWAY_UNREACHABLE")
    assert any(a["message"] == "平台 LLM 网关不可达" for a in mixed)
    assert all(a["message"] != PLAN_FULL_USER for a in mixed)
