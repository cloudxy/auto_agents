"""B-M3 消费面协议分发验证（工单 25）：llm_chat 按 protocol 路由 + usage 归一化

Seam（工单预确认）：llm_chat 公共签名（配置桩 + FakeAsyncClient 捕获请求）。
openai_compatible 路径字节级不变是硬验收（payload 键集恰等，无新增 max_tokens）。
"""
import pytest

import backend.services.ai_planner.llm_client as lc
from backend.services.llm_provider_service import LlmRuntimeConfig

BUSINESS_MAX_TOKENS = getattr(lc, "_BUSINESS_MAX_TOKENS", 4096)


def _cfg(protocol: str) -> LlmRuntimeConfig:
    return LlmRuntimeConfig(
        base_url="https://api.test", api_key="sk-x", model="m-1",
        temperature=0.2, timeout=5, max_retries=1, enabled=True,
        source="config", provider_id=None, protocol=protocol,
    )


def _patch_env(monkeypatch, resp_body: dict) -> dict:
    """注入：运行时配置桩 + 计量捕获 + 一次性 FakeAsyncClient（记录请求）"""
    env: dict = {"cfg": None, "requests": [], "usage": None}

    async def _resolve():
        return env["cfg"]

    async def _record(**kwargs):
        env["usage"] = kwargs

    async def _month(dim, **kw):
        return 0

    monkeypatch.setattr("backend.services.ai_planner_service._resolve_llm_runtime_config", _resolve)
    monkeypatch.setattr(lc, "record_usage", _record)
    monkeypatch.setattr(lc, "get_month_used", _month)

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None):
            env["requests"].append({"url": url, "json": json, "headers": headers})

            class _Resp:
                @staticmethod
                def raise_for_status():
                    return None

                @staticmethod
                def json():
                    return resp_body

            return _Resp()

    monkeypatch.setattr(lc.httpx, "AsyncClient", _Client)
    return env


MESSAGES = [{"role": "user", "content": "hi"}]


@pytest.mark.asyncio
async def test_openai_path_payload_byte_compatible(monkeypatch):
    """openai_compatible：URL/headers/payload 与改前完全一致（无 max_tokens 注入）"""
    env = _patch_env(monkeypatch, {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"total_tokens": 10, "prompt_tokens": 6, "completion_tokens": 4},
    })
    env["cfg"] = _cfg("openai_compatible")

    content = await lc.llm_chat(MESSAGES)
    assert content == "ok"
    req = env["requests"][0]
    assert req["url"] == "https://api.test/chat/completions"
    assert req["headers"]["Authorization"] == "Bearer sk-x"
    assert set(req["json"].keys()) == {"model", "messages", "temperature"}
    assert env["usage"]["prompt_tokens"] == 6
    assert env["usage"]["total_tokens"] == 10


@pytest.mark.asyncio
async def test_anthropic_routing_and_usage_normalized(monkeypatch):
    env = _patch_env(monkeypatch, {
        "content": [{"type": "text", "text": "bonjour"}],
        "usage": {"input_tokens": 6, "output_tokens": 4},
    })
    env["cfg"] = _cfg("anthropic")

    content = await lc.llm_chat(MESSAGES)
    assert content == "bonjour"
    req = env["requests"][0]
    assert req["url"] == "https://api.test/v1/messages"
    assert req["headers"]["x-api-key"] == "sk-x"
    assert req["json"]["max_tokens"] == BUSINESS_MAX_TOKENS
    # anthropic usage 归一化：input/output → prompt/completion，total=和
    assert env["usage"]["prompt_tokens"] == 6
    assert env["usage"]["completion_tokens"] == 4
    assert env["usage"]["total_tokens"] == 10


@pytest.mark.asyncio
async def test_gemini_routing_and_usage_normalized(monkeypatch):
    env = _patch_env(monkeypatch, {
        "candidates": [{"content": {"parts": [{"text": "hola"}]}}],
        "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3, "totalTokenCount": 8},
    })
    env["cfg"] = _cfg("google_gemini")

    content = await lc.llm_chat(MESSAGES)
    assert content == "hola"
    req = env["requests"][0]
    assert req["url"] == "https://api.test/v1beta/models/m-1:generateContent"
    assert req["headers"]["x-goog-api-key"] == "sk-x"
    assert env["usage"]["prompt_tokens"] == 5
    assert env["usage"]["completion_tokens"] == 3
    assert env["usage"]["total_tokens"] == 8


@pytest.mark.asyncio
async def test_resolve_runtime_config_carries_protocol(db_session, monkeypatch):
    """激活的 anthropic 供应商 → LlmRuntimeConfig.protocol 随行携带"""
    from cryptography.fernet import Fernet

    from platform_core.schemas.llm_provider import LlmProviderCreate

    from backend.services.llm_provider_service import LlmProviderService

    monkeypatch.setenv("LLM_ENCRYPTION_KEY", Fernet.generate_key().decode())
    async with db_session() as s:
        svc = LlmProviderService(s)
        await svc.create_provider(LlmProviderCreate(
            name="proto-check", provider_type="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-ant-test",
            model="claude-sonnet-4-6", temperature=0.2, timeout=60,
            max_retries=2, enabled=True,
        ))
        provider = await svc.repo.get_by_name("proto-check")
        provider.is_active = True
        await s.commit()

        cfg = await svc.resolve_runtime_config()
    assert cfg.protocol == "anthropic"
