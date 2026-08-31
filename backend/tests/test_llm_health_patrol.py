"""B-M4-2 周期巡检 + fail-closed 验证（工单 27）

Seam（工单预确认）：LlmHealthPatrol.patrol_once（monkeypatch test_model）+ 预算熔断门。
"""
import pytest

import backend.services.ai_planner.llm_client as lc
from platform_core.exceptions import BusinessException
from platform_core.models.llm_provider import LlmProvider
from platform_core.models.llm_provider_model import LlmProviderModel


async def _seed(db_session):
    async with db_session() as s:
        providers = [
            LlmProvider(name="p-on", provider_type="openai_compatible",
                        base_url="https://a", model="m1", enabled=True,
                        api_key_encrypted="enc-placeholder"),
            LlmProvider(name="p-off", provider_type="openai_compatible",
                        base_url="https://b", model="m1", enabled=False),
        ]
        s.add_all(providers)
        await s.flush()
        s.add_all([
            LlmProviderModel(provider_id=providers[0].id, model_id="m1", is_default=True),
            LlmProviderModel(provider_id=providers[0].id, model_id="m2"),
            LlmProviderModel(provider_id=providers[0].id, model_id="m3", enabled=False),
            LlmProviderModel(provider_id=providers[1].id, model_id="m1"),
        ])
        await s.commit()
        return providers[0].id, providers[1].id


@pytest.mark.asyncio
async def test_patrol_once_covers_enabled_providers_enabled_models(db_session, monkeypatch):
    """巡检批量刷新：enabled 供应商 × enabled 模型全覆盖；禁用供应商/禁用模型跳过"""
    from backend.services.llm_health_patrol import LlmHealthPatrol

    on_id, off_id = await _seed(db_session)
    calls: list[tuple[int, str]] = []

    async def _fake_test_model(self, provider_id, model_id):
        calls.append((provider_id, model_id))
        return {"ok": True, "latency_ms": 5, "model": model_id, "error": "", "health_status": "healthy"}

    monkeypatch.setattr(
        "backend.services.llm_provider_service.LlmProviderService.test_model", _fake_test_model
    )
    summary = await LlmHealthPatrol.patrol_once(session_factory=db_session)
    assert set(calls) == {(on_id, "m1"), (on_id, "m2")}
    assert (off_id, "m1") not in calls  # 禁用供应商跳过
    assert (on_id, "m3") not in calls   # 禁用模型跳过
    assert summary["providers"] == 1 and summary["models"] == 2


@pytest.mark.asyncio
async def test_patrol_skips_models_without_provider_key(monkeypatch):
    """无密钥供应商跳过外呼（避免批量 401 噪音）——summary 记 skipped"""
    from backend.services.llm_health_patrol import LlmHealthPatrol

    calls = []

    async def _fake_test_model(self, provider_id, model_id):
        calls.append((provider_id, model_id))
        return {"ok": True, "latency_ms": 1, "model": model_id, "error": "", "health_status": "healthy"}

    monkeypatch.setattr(
        "backend.services.llm_provider_service.LlmProviderService.test_model", _fake_test_model
    )

    class _Q:
        def __init__(self):
            from datetime import datetime
            self.row = LlmProvider(
                id=7, name="nokey", provider_type="openai_compatible",
                base_url="https://x", model="m", enabled=True, api_key_encrypted=None,
                created_at=datetime(2026, 8, 31), updated_at=None,
            )

    def _factory():
        class _S:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def commit(self):
                return None

            async def execute(self, *_a, **_kw):
                class _R:
                    def scalars(self_inner):
                        return self_inner

                    def all(self_inner):
                        return [_Q().row]
                return _R()

        return _S()

    summary = await LlmHealthPatrol.patrol_once(session_factory=_factory)
    assert calls == [] and summary["skipped_nokey"] >= 1


@pytest.mark.asyncio
async def test_budget_fail_closed_when_redis_unreachable(monkeypatch):
    """fail-closed（LLM.BUDGET_FAIL_CLOSED=true）：预算读数不可用即拒绝 LLM 调用；
    默认（false）保持内存回退语义（CI 无 Redis 可跑）。"""
    from backend.services.llm_provider_service import LlmRuntimeConfig

    cfg = LlmRuntimeConfig(
        base_url="https://api.test", api_key="sk-x", model="m",
        temperature=0.2, timeout=5, max_retries=1, enabled=True,
        source="config", provider_id=None,
    )

    async def _resolve():
        return cfg

    async def _month_returning_none(dim):
        return None  # Redis 不可达时的现存语义

    monkeypatch.setattr("backend.services.ai_planner_service._resolve_llm_runtime_config", _resolve)
    monkeypatch.setattr(lc, "get_month_used", _month_returning_none)

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            raise AssertionError("fail-closed 时不应发起调用")

    monkeypatch.setattr(lc.httpx, "AsyncClient", _Client)

    from config import settings

    original = settings.get("LLM.BUDGET_FAIL_CLOSED")
    settings.set("LLM.BUDGET_FAIL_CLOSED", True)
    try:
        with pytest.raises(BusinessException, match="fail-closed|预算读数"):
            await lc.llm_chat([{"role": "user", "content": "hi"}])
    finally:
        settings.set("LLM.BUDGET_FAIL_CLOSED", original)


def test_patrol_lock_key_in_queues_contract():
    from platform_core import queues

    assert queues.LLM_PATROL_LOCK == "llm:patrol:lock"
