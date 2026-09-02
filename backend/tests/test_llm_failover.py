"""B-M4-1 故障转移候选链 + 降质告警验证（工单 26）

Seam（工单预确认）：llm_chat 公共签名（透明故障转移，调用方无感）+
_candidate_chain（注入 session）。不含用量表迁移（D9 归 S1）。
"""
import pytest

import backend.services.ai_planner.llm_client as lc
from backend.services.llm_provider_service import LlmRuntimeConfig
from platform_core.exceptions import BusinessException

MESSAGES = [{"role": "user", "content": "hi"}]


def _cfg(provider_id=1, model="m-default"):
    return LlmRuntimeConfig(
        base_url="https://api.test", api_key="sk-x", model=model,
        temperature=0.2, timeout=5, max_retries=1, enabled=True,
        source=f"provider:{provider_id}", provider_id=provider_id,
    )


def _patch(monkeypatch, cfg, chain, http_behavior, notifications):
    """注入：配置桩 / 候选链桩 / 按 payload.model 分流的 httpx / NotifyService 桩"""

    async def _resolve():
        return cfg

    monkeypatch.setattr("backend.services.ai_planner_service._resolve_llm_runtime_config", _resolve)
    # 共享 client 缓存跨测试会残留旧闭包，逐用例清空（provider 路径专用缓存）
    lc._HTTP_CLIENTS.clear()
    lc._HTTP_CLIENT_OWNER.clear()

    async def _chain(pid, session=None):
        return chain

    monkeypatch.setattr(lc, "_candidate_chain", _chain)

    async def _record(**kw):
        return None

    async def _month(dim, **kw):
        return 0

    monkeypatch.setattr(lc, "record_usage", _record)
    monkeypatch.setattr(lc, "get_month_used", _month)

    class _Client:
        is_closed = False  # get_shared_client 缓存健康检查依赖

        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None):
            outcome = http_behavior(json["model"])
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(lc.httpx, "AsyncClient", _Client)

    class _Notify:
        async def notify_text(self, event, text):
            notifications.append({"event": event, "text": text})

    monkeypatch.setattr("backend.services.notify_service.NotifyService", _Notify)


def _ok_response(text="ok"):
    class _Resp:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": text}}],
                    "usage": {"total_tokens": 3, "prompt_tokens": 2, "completion_tokens": 1}}

    return _Resp()


class _NetErr(Exception):
    pass


@pytest.mark.asyncio
async def test_primary_failure_falls_over_to_backup(monkeypatch):
    """主模型故障 → 次选接管，调用方无感成功"""
    notes: list = []
    _patch(
        monkeypatch,
        cfg=_cfg(model="m-default"),
        chain=[("m-backup", "basic")],
        http_behavior=lambda m: _NetErr("boom") if m == "m-default" else _ok_response("from-backup"),
        notifications=notes,
    )
    content = await lc.llm_chat(MESSAGES, usage_dim="skill_scoring")
    assert content == "from-backup"


@pytest.mark.asyncio
async def test_tier_degrade_alert_fires_only_on_downgrade(monkeypatch):
    """strong→basic 切换发降质告警；strong→strong 同级切换不告警（负向）"""
    notes: list = []
    _patch(
        monkeypatch,
        cfg=_cfg(model="m-strong"),
        chain=[("m-strong", "strong"), ("m-strong2", "strong")],
        http_behavior=lambda m: _NetErr("x") if m == "m-strong" else _ok_response("same-tier"),
        notifications=notes,
    )
    assert await lc.llm_chat(MESSAGES) == "same-tier"
    assert notes == []  # 同级不告警

    notes2: list = []
    _patch(
        monkeypatch,
        cfg=_cfg(model="m-strong"),
        chain=[("m-strong", "strong"), ("m-basic", "basic")],
        http_behavior=lambda m: _NetErr("x") if m == "m-strong" else _ok_response("downgraded"),
        notifications=notes2,
    )
    assert await lc.llm_chat(MESSAGES) == "downgraded"
    assert len(notes2) == 1 and "降质" in notes2[0]["text"]


@pytest.mark.asyncio
async def test_all_candidates_exhausted_raises_summary(monkeypatch):
    """全候选耗尽：结构化失败（含各候选错误摘要；脱敏——只含异常类名/网络错误文本）"""
    notes: list = []
    _patch(
        monkeypatch,
        cfg=_cfg(model="m-default"),
        chain=[("m-default", "basic"), ("m-a", "basic"), ("m-b", "basic")],
        http_behavior=lambda m: _NetErr("timeout-sim"),
        notifications=notes,
    )
    with pytest.raises(BusinessException) as ei:
        await lc.llm_chat(MESSAGES)
    message = str(ei.value)
    assert "候选" in message and "m-a" in message and "m-b" in message


@pytest.mark.asyncio
async def test_candidate_chain_filters_disabled_and_down(db_session):
    """候选链查询：enabled=False / health=down 被跳过，priority 升序，默认行首位"""
    from platform_core.models.llm_provider import LlmProvider
    from platform_core.models.llm_provider_model import LlmProviderModel

    async with db_session() as s:
        provider = LlmProvider(name="fo", provider_type="openai_compatible",
                               base_url="https://x", model="m-default")
        s.add(provider)
        await s.flush()
        pid = provider.id
        rows = [
            LlmProviderModel(provider_id=pid, model_id="m-default", priority=100, is_default=True),
            LlmProviderModel(provider_id=pid, model_id="m-down", priority=10, health_status="down"),
            LlmProviderModel(provider_id=pid, model_id="m-off", priority=10, enabled=False),
            LlmProviderModel(provider_id=pid, model_id="m-low", priority=50),
            LlmProviderModel(provider_id=pid, model_id="m-high", priority=5),
        ]
        s.add_all(rows)
        await s.commit()

    async with db_session() as s:
        chain = await lc._candidate_chain(pid, session=s)
    assert [m for m, _ in chain] == ["m-default", "m-high", "m-low"]
