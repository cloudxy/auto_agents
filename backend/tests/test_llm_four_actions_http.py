"""T-16 四动作现网 HTTP 分格（禁止 or_cell_failure 一名三格）。

成功格等到 outbound=网关 URL。失败格只钉该格那一句，禁止 outbound oracle。
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from backend.services.ai_planner.orchestrator import AiPlannerService
from backend.services.quota_service import (
    NO_MODEL_USER,
    PLAN_FULL_CTA,
    PLAN_FULL_USER,
    GATEWAY_UNREACHABLE_USER,
    shanghai_today,
)
from platform_core.models.ai_plan import AiPlan
from platform_core.models.llm_token_usage import LlmTokenUsage
from platform_core.models.skill import Skill, SkillJob
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

GATEWAY_URL = "http://gw.test"
PLAN_JSON = json.dumps({
    "selectors": [{"name": "title", "type": "css", "expr": "h1::text"}],
    "pagination": {"selector": "a.next", "type": "css", "max_pages": 2},
    "detail": None,
    "filters": [],
})
SCORE_JSON = json.dumps({
    "completeness": 8, "doc_quality": 7, "maintenance": 6, "real_world_effect": 7,
    "overall": 7,
    "rationale": {
        "completeness": "全", "doc_quality": "清",
        "maintenance": "活", "real_world_effect": "效",
    },
    "notes": "总体可用",
})


@pytest.fixture
def t16_plane(monkeypatch):
    from config import settings

    prev = {
        "LLM.DATA_PLANE": settings.get("LLM.DATA_PLANE"),
        "LITELLM.BASE_URL": settings.get("LITELLM.BASE_URL"),
        "LITELLM.MASTER_KEY": settings.get("LITELLM.MASTER_KEY"),
        "LLM.MAX_RETRIES": settings.get("LLM.MAX_RETRIES"),
    }
    settings.set("LLM.DATA_PLANE", "litellm")
    settings.set("LITELLM.BASE_URL", GATEWAY_URL)
    settings.set("LITELLM.MASTER_KEY", "sk-virt")
    settings.set("LLM.MAX_RETRIES", 1)

    async def _sleep(*_a, **_k):
        return None

    monkeypatch.setattr("backend.services.ai_planner.llm_client.asyncio.sleep", _sleep)

    async def _month(*_a, **_k):
        return 0

    monkeypatch.setattr("backend.services.ai_planner.llm_client.get_month_used", _month)
    yield
    for key, value in prev.items():
        if value is not None:
            settings.set(key, value)


def _install_llm_seams(monkeypatch) -> None:
    async def _sleep(*_a, **_k):
        return None

    monkeypatch.setattr("backend.services.ai_planner.llm_client.asyncio.sleep", _sleep)

    async def _month(*_a, **_k):
        return 0

    monkeypatch.setattr("backend.services.ai_planner.llm_client.get_month_used", _month)


def _forbid_yml(monkeypatch) -> None:
    def _boom():
        raise AssertionError("SH-16: except 禁止 resolve_config_from_settings")

    monkeypatch.setattr(
        "backend.services.ai_planner.llm_client.resolve_config_from_settings", _boom,
    )


def _install_gateway(monkeypatch, mode: str, outbound: list, chat_content: str) -> None:
    async def _http(method, path, **_kw):
        url = f"{GATEWAY_URL}{path}"
        if method == "GET" and path == "/v1/models":
            if mode == "unreachable":
                raise httpx.ConnectError("connection refused")
            if mode == "no_model":
                return {"data": []}
            return {"data": [{"id": "gpt-4o-mini"}]}
        if method == "POST" and path == "/v1/chat/completions":
            if mode == "no_model":
                raise AssertionError("empty model must not POST chat")
            if mode == "unreachable":
                raise httpx.ConnectError("connection refused")
            outbound.append(url)
            return {
                "choices": [{"message": {"content": chat_content}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        raise AssertionError(f"unexpected {method} {path}")

    monkeypatch.setattr("backend.services.llm_gateway._settings._http_json", _http)
    monkeypatch.setattr("backend.services.llm_gateway.chat._http_json", _http)


def _install_engines(monkeypatch, db_engine, db_session) -> None:
    import backend.services.ai_planner_service as aps

    class _Mgr:
        async_engines = {"DEFAULT": db_engine}

    monkeypatch.setattr(aps, "get_manager", lambda: _Mgr())
    monkeypatch.setattr(aps, "quota_session_factory", db_session, raising=False)


def _patch_wait_bg(monkeypatch) -> None:
    from backend.services.ai_planner.state import _BACKGROUND_TASKS

    orig_plan = AiPlannerService.launch_plan
    orig_test = AiPlannerService.launch_test

    async def _drain(orig, self, plan_id):
        await orig(self, plan_id)
        pending = [t for t in list(_BACKGROUND_TASKS) if not t.done()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        return await self.get_plan(plan_id)

    async def launch_plan(self, plan_id):
        return await _drain(orig_plan, self, plan_id)

    async def launch_test(self, plan_id):
        return await _drain(orig_test, self, plan_id)

    monkeypatch.setattr(AiPlannerService, "launch_plan", launch_plan)
    monkeypatch.setattr(AiPlannerService, "launch_test", launch_test)


def _operator_headers(db_session, slug: str, quota: dict | None = None):
    from backend.services.auth_service import AuthService

    async def _go():
        async with db_session() as s:
            t = Tenant(slug=slug, name=slug, quota=quota)
            s.add(t)
            await s.flush()
            u = User(
                username=f"{slug}-op", email=f"{slug}@x.local", password_hash="x",
                role="operator", tenant_id=t.id, tenant_role="operator",
            )
            s.add(u)
            await s.commit()
            token = await AuthService(s).create_token({
                "id": u.id, "username": u.username, "is_admin": False,
                "role": "operator", "tenant_id": t.id, "tenant_role": "operator",
                "is_platform_admin": False,
            })
            return {"Authorization": f"Bearer {token.access_token}"}, int(t.id)

    return asyncio.run(_go())


def _create_plan(db_client, headers) -> int:
    resp = db_client.post(
        "/api/v1/ai/plans",
        headers=headers,
        json={"target_url": "https://example.com/list", "html_snippet": "<html><h1>t</h1></html>"},
    )
    assert resp.status_code in (200, 201)
    return int(resp.json()["data"]["id"])


def _get_plan(db_client, headers, plan_id: int) -> dict:
    resp = db_client.get(f"/api/v1/ai/plans/{plan_id}", headers=headers)
    assert resp.status_code == 200
    return resp.json()["data"]


def _assert_only_sentence(text: str, sentence: str, *forbidden: str) -> None:
    assert text == sentence
    for item in forbidden:
        assert item not in text
    assert "QUOTA_EXCEEDED" not in text


def _wire_plan(monkeypatch, db_engine, db_session, mode: str, outbound: list, content: str) -> None:
    _forbid_yml(monkeypatch)
    _install_engines(monkeypatch, db_engine, db_session)
    _install_gateway(monkeypatch, mode, outbound, content)
    _patch_wait_bg(monkeypatch)


def test_post_plan_outbound_gateway(
    db_client, db_engine, db_session, monkeypatch, t16_plane,
):
    """GWT-70.1 only：等到 outbound=网关 URL。禁止 HTTP 200 / planning 勾。"""
    outbound: list[str] = []
    _wire_plan(monkeypatch, db_engine, db_session, "ok", outbound, PLAN_JSON)
    headers, _tid = _operator_headers(db_session, "t16-70-1")
    pid = _create_plan(db_client, headers)
    db_client.post(f"/api/v1/ai/plans/{pid}/plan", headers=headers)
    assert outbound == [f"{GATEWAY_URL}/v1/chat/completions"]
    assert "https://pub" not in outbound[0]
    assert "api.openai.com" not in outbound[0]


def test_post_plan_no_model_only_70_2(
    db_client, db_engine, db_session, monkeypatch, t16_plane,
):
    """GWT-70.2 only：error_message 只「还没有平台模型」。禁止 outbound oracle。"""
    outbound: list[str] = []
    _wire_plan(monkeypatch, db_engine, db_session, "no_model", outbound, PLAN_JSON)
    headers, _tid = _operator_headers(db_session, "t16-70-2")
    pid = _create_plan(db_client, headers)
    db_client.post(f"/api/v1/ai/plans/{pid}/plan", headers=headers)
    data = _get_plan(db_client, headers, pid)
    assert data["status"] == "failed"
    _assert_only_sentence(
        data["error_message"], NO_MODEL_USER, GATEWAY_UNREACHABLE_USER, PLAN_FULL_USER,
    )
    assert outbound == []


def test_post_plan_unreachable_only_74_1(
    db_client, db_engine, db_session, monkeypatch, t16_plane,
):
    """GWT-74.1 only：error_message 只「平台 LLM 网关不可达」。"""
    outbound: list[str] = []
    _wire_plan(monkeypatch, db_engine, db_session, "unreachable", outbound, PLAN_JSON)
    headers, _tid = _operator_headers(db_session, "t16-74-1")
    pid = _create_plan(db_client, headers)
    db_client.post(f"/api/v1/ai/plans/{pid}/plan", headers=headers)
    data = _get_plan(db_client, headers, pid)
    assert data["status"] == "failed"
    _assert_only_sentence(
        data["error_message"], GATEWAY_UNREACHABLE_USER, NO_MODEL_USER, PLAN_FULL_USER,
    )
    assert outbound == []


def test_post_plan_resolve_exception_outbound_is_gateway(
    db_client, db_engine, db_session, monkeypatch, t16_plane,
):
    """SH-18：resolve 抛错后 outbound 是网关 URL（不勾 74.1）。"""
    outbound: list[str] = []
    _wire_plan(monkeypatch, db_engine, db_session, "ok", outbound, PLAN_JSON)

    async def _boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(
        "backend.services.ai_planner.llm_client.resolve_own_tenant_config", _boom,
    )
    headers, _tid = _operator_headers(db_session, "t16-sh18")
    pid = _create_plan(db_client, headers)
    db_client.post(f"/api/v1/ai/plans/{pid}/plan", headers=headers)
    assert outbound == [f"{GATEWAY_URL}/v1/chat/completions"]
    data = _get_plan(db_client, headers, pid)
    assert data.get("error_message") != GATEWAY_UNREACHABLE_USER


def _patch_repair_first_fail(monkeypatch) -> dict:
    import backend.services.ai_planner_service as aps
    from backend.services.ai_planner.state import _TaskSnapshot
    from platform_core.schemas.spider import TaskQualityReportResponse

    class _Spider:
        def __init__(self, session):
            self.session = session

        async def enqueue(self, **_kw):
            return SimpleNamespace(id=91, status="pending")

        async def get_task_quality(self, task_id):
            return TaskQualityReportResponse(
                task_id=task_id, avg_score=90.0, total_items=3,
            )

    monkeypatch.setattr(aps, "SpiderService", _Spider)
    calls = {"n": 0}

    async def _wait(self, spider_svc, task_id):
        calls["n"] += 1
        if calls["n"] == 1:
            return _TaskSnapshot(
                task_id=task_id, status="failed", result_count=0, error_message="empty",
            )
        return _TaskSnapshot(
            task_id=task_id, status="completed", result_count=3, error_message=None,
        )

    monkeypatch.setattr(AiPlannerService, "_wait_task_final", _wait)
    return calls


def _seed_test_plan(db_session, tid: int) -> int:
    async def _go():
        async with db_session() as s:
            plan = AiPlan(
                target_url="https://example.com/list",
                status="draft",
                tenant_id=tid,
                generated_params={
                    "urls": ["https://example.com/list"],
                    "selectors": [{"name": "title", "type": "css", "expr": "h1::text"}],
                },
                plan_json={
                    "flow": {
                        "selectors": [{"name": "title", "type": "css", "expr": "h1::text"}],
                        "pagination": None, "detail": None, "filters": [],
                    },
                    "html_sample": "<html><h1>t</h1></html>",
                    "test_history": [],
                },
            )
            s.add(plan)
            await s.commit()
            await s.refresh(plan)
            return int(plan.id)

    return asyncio.run(_go())


def test_post_test_enters_repair_flow_outbound_gateway(
    db_client, db_engine, db_session, monkeypatch, t16_plane,
):
    """GWT-70.5 only：第一次失败进 _repair_flow，等到 outbound=网关 URL。"""
    outbound: list[str] = []
    _wire_plan(monkeypatch, db_engine, db_session, "ok", outbound, PLAN_JSON)
    calls = _patch_repair_first_fail(monkeypatch)
    headers, tid = _operator_headers(db_session, "t16-70-5")
    pid = _seed_test_plan(db_session, tid)
    db_client.post(f"/api/v1/ai/plans/{pid}/test", headers=headers)
    assert calls["n"] >= 1
    assert outbound == [f"{GATEWAY_URL}/v1/chat/completions"]


def test_post_test_enters_repair_flow_no_model_only_70_8(
    db_client, db_engine, db_session, monkeypatch, t16_plane,
):
    """GWT-70.8 only：_repair_flow 后 error_message 只「还没有平台模型」。"""
    outbound: list[str] = []
    _wire_plan(monkeypatch, db_engine, db_session, "no_model", outbound, PLAN_JSON)
    calls = _patch_repair_first_fail(monkeypatch)
    headers, tid = _operator_headers(db_session, "t16-70-8")
    pid = _seed_test_plan(db_session, tid)
    db_client.post(f"/api/v1/ai/plans/{pid}/test", headers=headers)
    assert calls["n"] >= 1
    data = _get_plan(db_client, headers, pid)
    assert data["status"] == "failed"
    _assert_only_sentence(
        data["error_message"], NO_MODEL_USER, GATEWAY_UNREACHABLE_USER, PLAN_FULL_USER,
    )
    assert outbound == []


def test_post_test_enters_repair_flow_unreachable_only_74_4(
    db_client, db_engine, db_session, monkeypatch, t16_plane,
):
    """GWT-74.4 only：_repair_flow 后 error_message 只「平台 LLM 网关不可达」。"""
    outbound: list[str] = []
    _wire_plan(monkeypatch, db_engine, db_session, "unreachable", outbound, PLAN_JSON)
    calls = _patch_repair_first_fail(monkeypatch)
    headers, tid = _operator_headers(db_session, "t16-74-4")
    pid = _seed_test_plan(db_session, tid)
    db_client.post(f"/api/v1/ai/plans/{pid}/test", headers=headers)
    assert calls["n"] >= 1
    data = _get_plan(db_client, headers, pid)
    assert data["status"] == "failed"
    _assert_only_sentence(
        data["error_message"], GATEWAY_UNREACHABLE_USER, NO_MODEL_USER, PLAN_FULL_USER,
    )
    assert outbound == []


class _FakeQueueRedis:
    def __init__(self):
        self.items: list[str] = []

    async def lpush(self, key, value):
        self.items.insert(0, value)
        return len(self.items)

    async def rpop(self, key):
        return self.items.pop() if self.items else None


def _install_score_queue(monkeypatch) -> _FakeQueueRedis:
    fake = _FakeQueueRedis()

    async def _fake_redis(key: str = "DEFAULT"):
        return fake

    monkeypatch.setattr("backend.services.skill_scoring_service.get_async_redis", _fake_redis)
    monkeypatch.setattr("platform_core.redis_async.get_async_redis", _fake_redis)
    return fake


def _seed_skill(db_session, name: str = "rate-me") -> str:
    async def _go():
        async with db_session() as s:
            s.add(Skill(
                name=name, title="R", category="document",
                file_path=f"skills/{name}", description="待评分",
            ))
            await s.commit()
        return name

    return asyncio.run(_go())


def _consume_once(db_session) -> tuple[dict, SkillJob | None]:
    from backend.services.skill_scoring_service import SkillScoringService
    from sqlalchemy import select

    async def _go():
        async with db_session() as s:
            result = await SkillScoringService(s).consume_once()
            await s.commit()
            job = (await s.execute(select(SkillJob).order_by(SkillJob.id.desc()))).scalars().first()
            return result, job

    return asyncio.run(_go())


def test_post_rescore_consume_once_outbound_gateway(
    db_client, db_engine, db_session, monkeypatch, t16_plane,
):
    """GWT-70.6 only：POST /rescore 后 consume_once，等到 outbound=网关 URL。"""
    outbound: list[str] = []
    _wire_plan(monkeypatch, db_engine, db_session, "ok", outbound, SCORE_JSON)
    _install_score_queue(monkeypatch)
    headers, _tid = _operator_headers(db_session, "t16-70-6")
    name = _seed_skill(db_session)
    resp = db_client.post(f"/api/v1/skills/{name}/rescore", headers=headers)
    result, _job = _consume_once(db_session)
    assert result.get("status") == "scored"
    assert outbound == [f"{GATEWAY_URL}/v1/chat/completions"]
    assert resp.status_code == 200  # 入队不是 Then；Then 是 outbound


def test_post_rescore_consume_once_no_model_only_70_9(
    db_client, db_engine, db_session, monkeypatch, t16_plane,
):
    """GWT-70.9 only：consume_once 的 job/响应只「还没有平台模型」。"""
    outbound: list[str] = []
    _wire_plan(monkeypatch, db_engine, db_session, "no_model", outbound, SCORE_JSON)
    _install_score_queue(monkeypatch)
    headers, _tid = _operator_headers(db_session, "t16-70-9")
    name = _seed_skill(db_session, "rate-me-empty")
    db_client.post(f"/api/v1/skills/{name}/rescore", headers=headers)
    result, job = _consume_once(db_session)
    assert result["status"] == "failed"
    _assert_only_sentence(
        result["error"], NO_MODEL_USER, GATEWAY_UNREACHABLE_USER, PLAN_FULL_USER,
    )
    assert job is not None and job.status == "failed"
    _assert_only_sentence(
        str(job.detail.get("reason")), NO_MODEL_USER, GATEWAY_UNREACHABLE_USER,
    )
    assert outbound == []


def test_post_rescore_consume_once_unreachable_only_74_5(
    db_client, db_engine, db_session, monkeypatch, t16_plane,
):
    """GWT-74.5 only：consume_once 的 job/响应只「平台 LLM 网关不可达」。"""
    outbound: list[str] = []
    _wire_plan(monkeypatch, db_engine, db_session, "unreachable", outbound, SCORE_JSON)
    _install_score_queue(monkeypatch)
    headers, _tid = _operator_headers(db_session, "t16-74-5")
    name = _seed_skill(db_session, "rate-me-down")
    db_client.post(f"/api/v1/skills/{name}/rescore", headers=headers)
    result, job = _consume_once(db_session)
    assert result["status"] == "failed"
    _assert_only_sentence(
        result["error"], GATEWAY_UNREACHABLE_USER, NO_MODEL_USER, PLAN_FULL_USER,
    )
    assert job is not None and job.status == "failed"
    _assert_only_sentence(
        str(job.detail.get("reason")), GATEWAY_UNREACHABLE_USER, NO_MODEL_USER,
    )
    assert outbound == []


def _seed_quota_full(db_session, tid: int) -> None:
    async def _go():
        async with db_session() as s:
            s.add(LlmTokenUsage(
                tenant_id=tid, provider_name="p", model="m",
                stat_date=shanghai_today(), total_tokens=150,
            ))
            await s.commit()

    asyncio.run(_go())


def test_post_plan_quota_full_gateway_reachable_only_12_3(
    db_client, db_engine, db_session, monkeypatch, t16_plane,
):
    """GWT-74.2 / 12.3：满额 + 网关可达 → 只 12.3 句，不是网关不可达。"""
    outbound: list[str] = []
    _wire_plan(monkeypatch, db_engine, db_session, "ok", outbound, PLAN_JSON)
    headers, tid = _operator_headers(
        db_session, "t16-74-2a", quota={"llm_tokens_month": 100},
    )
    _seed_quota_full(db_session, tid)
    pid = _create_plan(db_client, headers)
    resp = db_client.post(f"/api/v1/ai/plans/{pid}/plan", headers=headers)
    assert resp.status_code == 400, resp.text
    msg = resp.json()["message"]
    assert PLAN_FULL_USER in msg and PLAN_FULL_CTA in msg
    assert GATEWAY_UNREACHABLE_USER not in msg
    assert NO_MODEL_USER not in msg
    assert "QUOTA_EXCEEDED" not in msg
    assert "采集未运行，不会出数" not in msg
    assert outbound == []
    data = _get_plan(db_client, headers, pid)
    assert data["status"] == "draft"


def test_post_plan_quota_full_gateway_unreachable_only_12_3(
    db_client, db_engine, db_session, monkeypatch, t16_plane,
):
    """GWT-74.2 / 12.3：满额 + 网关不可达 → 仍只 12.3 句。"""
    outbound: list[str] = []
    _wire_plan(monkeypatch, db_engine, db_session, "unreachable", outbound, PLAN_JSON)
    headers, tid = _operator_headers(
        db_session, "t16-74-2b", quota={"llm_tokens_month": 100},
    )
    _seed_quota_full(db_session, tid)
    pid = _create_plan(db_client, headers)
    resp = db_client.post(f"/api/v1/ai/plans/{pid}/plan", headers=headers)
    assert resp.status_code == 400, resp.text
    msg = resp.json()["message"]
    assert PLAN_FULL_USER in msg and PLAN_FULL_CTA in msg
    assert GATEWAY_UNREACHABLE_USER not in msg
    assert NO_MODEL_USER not in msg
    assert "QUOTA_EXCEEDED" not in msg
    assert "采集未运行，不会出数" not in msg
    assert outbound == []
    data = _get_plan(db_client, headers, pid)
    assert data["status"] == "draft"
