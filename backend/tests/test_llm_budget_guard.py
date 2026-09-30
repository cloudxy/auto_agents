"""平台 LLM 预算闸（审计 R2-8 / R2-10 / P0-10 回归）

原缺陷：网关路径读数不可用时恒 fail-open（无视 prod 的 BUDGET_FAIL_CLOSED=true），
两条路径各写一份预算判定且口径漂移。现两条路径共用 _budget_guard。
"""
from __future__ import annotations

import asyncio

import pytest

import backend.services.ai_planner.llm_client as lc
from backend.services.llm_common.runtime import LlmRuntimeConfig
from platform_core.exceptions import BusinessException


def _cfg(source: str = "gateway") -> LlmRuntimeConfig:
    return LlmRuntimeConfig(
        base_url="http://gw.test", api_key="k", model="m", temperature=0.1,
        timeout=5.0, max_retries=2, enabled=True, source=source,
    )


@pytest.fixture
def fail_closed():
    from config import settings

    original = settings.get("LLM.BUDGET_FAIL_CLOSED")
    settings.set("LLM.BUDGET_FAIL_CLOSED", True)
    yield
    settings.set("LLM.BUDGET_FAIL_CLOSED", original)


def _unavailable(monkeypatch):
    async def _none(*_a, **_kw):
        return None
    monkeypatch.setattr(lc, "get_month_used", _none)


def test_guard_fail_closed_rejects_when_reading_unavailable(monkeypatch, fail_closed):
    _unavailable(monkeypatch)
    with pytest.raises(BusinessException) as exc:
        asyncio.run(lc._budget_guard("config", 1000, None))
    assert exc.value.code == "LLM_BUDGET_UNAVAILABLE"


def test_guard_fail_open_falls_back_to_memory(monkeypatch):
    _unavailable(monkeypatch)
    assert asyncio.run(lc._budget_guard("dim-fresh-x", 1000, None)) == 0


def test_guard_fuses_when_budget_exhausted(monkeypatch):
    async def _used(*_a, **_kw):
        return 1000
    monkeypatch.setattr(lc, "get_month_used", _used)
    with pytest.raises(BusinessException) as exc:
        asyncio.run(lc._budget_guard("config", 1000, 7))
    assert exc.value.code == "LLM_COST_FUSE"


def test_gateway_path_honours_fail_closed_without_outbound(monkeypatch, fail_closed):
    """网关路径：读数不可用 + fail-closed → 拒绝，且零出站（原先放行并真实调用）"""
    _unavailable(monkeypatch)
    outbound: list[dict] = []

    async def _models(_timeout):
        return ["m"]

    async def _chat(payload, timeout):
        outbound.append(payload)
        return {"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 1}}

    monkeypatch.setattr(lc, "_probe_gateway_models", _models)
    monkeypatch.setattr(lc, "chat_completions", _chat)
    with pytest.raises(BusinessException) as exc:
        asyncio.run(lc._llm_chat_gateway(
            [{"role": "user", "content": "hi"}], _cfg(),
            usage_dim=None, budget_override=None, model_override=None,
        ))
    assert exc.value.code == "LLM_BUDGET_UNAVAILABLE"
    assert outbound == []


# ---- 决策 D21：平台全局日预算上限（免费档可用平台 LLM 的前置闸之一） ----

@pytest.fixture
def daily_cap():
    from config import settings

    original = settings.get("LLM.PLATFORM_DAILY_TOKEN_CAP")
    settings.set("LLM.PLATFORM_DAILY_TOKEN_CAP", 1000)
    yield
    settings.set("LLM.PLATFORM_DAILY_TOKEN_CAP", original)


def _month(monkeypatch, value=0):
    async def _v(*_a, **_kw):
        return value
    monkeypatch.setattr(lc, "get_month_used", _v)


def _day(monkeypatch, value):
    async def _v(*_a, **_kw):
        return value
    monkeypatch.setattr(lc, "get_platform_day_used", _v)


def test_daily_cap_blocks_when_platform_spent_today(monkeypatch, daily_cap):
    _month(monkeypatch)
    _day(monkeypatch, 1000)
    with pytest.raises(BusinessException) as exc:
        asyncio.run(lc._budget_guard("config", 10**9, 7))
    assert exc.value.code == "LLM_PLATFORM_DAILY_CAP"
    assert "明天" in exc.value.message


def test_daily_cap_allows_under_limit(monkeypatch, daily_cap):
    _month(monkeypatch)
    _day(monkeypatch, 999)
    assert asyncio.run(lc._budget_guard("config", 10**9, 7)) == 0


def test_daily_cap_unreadable_follows_fail_closed(monkeypatch, daily_cap, fail_closed):
    _month(monkeypatch)
    _day(monkeypatch, None)
    with pytest.raises(BusinessException) as exc:
        asyncio.run(lc._budget_guard("config", 10**9, 7))
    assert exc.value.code == "LLM_BUDGET_UNAVAILABLE"


def test_daily_cap_zero_means_off(monkeypatch):
    from config import settings

    original = settings.get("LLM.PLATFORM_DAILY_TOKEN_CAP")
    settings.set("LLM.PLATFORM_DAILY_TOKEN_CAP", 0)
    try:
        _month(monkeypatch)
        _day(monkeypatch, 10**12)
        assert asyncio.run(lc._budget_guard("config", 10**9, 7)) == 0
    finally:
        settings.set("LLM.PLATFORM_DAILY_TOKEN_CAP", original)


def test_planning_prompt_input_is_capped(monkeypatch):
    """决策 D21 前置闸：送进 LLM 的页面 HTML 有长度上限（可配），超长截断"""
    from config import settings
    from backend.services.ai_planner.url_guard import _clean_html_sync

    original = settings.get("AI_PLANNER.MAX_HTML_CHARS")
    settings.set("AI_PLANNER.MAX_HTML_CHARS", 500)
    try:
        cleaned = _clean_html_sync("<div>" + "字" * 5000 + "</div>")
    finally:
        settings.set("AI_PLANNER.MAX_HTML_CHARS", original)
    assert len(cleaned) == 500
