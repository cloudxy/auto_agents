"""B-M1-1 协议适配器层验证（工单 20）：三协议全矩阵（MockTransport 固定样例报文）

Seam（工单预确认）：适配器公共方法（list_models/build_chat/parse_chat/is_chat_model）。
期望值全部来自各平台公开 API 文档形态的字面量样例（独立事实源）。
"""
import httpx
import pytest

from backend.services.llm_protocol import (
    AnthropicAdapter, GoogleGeminiAdapter, OpenAICompatibleAdapter, ProtocolError,
    get_adapter,
)

OPENAI_MODELS_BODY = {
    "object": "list",
    "data": [
        {"id": "gpt-4o", "object": "model", "owned_by": "openai"},
        {"id": "gpt-4o-mini", "object": "model", "owned_by": "openai"},
        {"id": "text-embedding-3-small", "object": "model", "owned_by": "openai"},
    ],
}

ANTHROPIC_MODELS_BODY = {
    "data": [
        {"id": "claude-sonnet-4-6", "display_name": "Claude Sonnet 4.6", "type": "model"},
        {"id": "claude-haiku-4-5", "display_name": "Claude Haiku 4.5", "type": "model"},
    ],
    "first_id": "claude-haiku-4-5", "last_id": "claude-sonnet-4-6", "has_more": False,
}

GEMINI_MODELS_BODY = {
    "models": [
        {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent", "countTokens"]},
        {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent", "countTokens"]},
        {"name": "models/gemini-2.5-pro", "supportedGenerationMethods": ["generateContent"]},
    ],
}


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)


class TestOpenAICompatible:
    @pytest.mark.asyncio
    async def test_list_models_parses_ids_and_chat_filter(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json=OPENAI_MODELS_BODY, request=request)

        adapter = OpenAICompatibleAdapter()
        async with _client(handler) as client:
            models = await adapter.list_models("https://api.test/v1", "sk-x", client=client)
        assert [m.id for m in models] == ["gpt-4o", "gpt-4o-mini", "text-embedding-3-small"]
        assert seen["url"] == "https://api.test/v1/models"
        assert seen["auth"] == "Bearer sk-x"
        assert adapter.chat_only(models).ids() == ["gpt-4o", "gpt-4o-mini"]

    def test_build_and_parse_chat(self):
        adapter = OpenAICompatibleAdapter()
        req = adapter.build_chat(
            "https://api.test/v1", "sk-x", "gpt-4o", [{"role": "user", "content": "ping"}], max_tokens=1
        )
        assert req.url == "https://api.test/v1/chat/completions"
        assert req.headers["Authorization"] == "Bearer sk-x"
        assert req.json_payload["model"] == "gpt-4o"
        assert req.json_payload["max_tokens"] == 1
        assert adapter.parse_chat({"choices": [{"message": {"content": "pong"}}]}) == "pong"


class TestAnthropic:
    @pytest.mark.asyncio
    async def test_list_models_headers_and_ids(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["key"] = request.headers.get("x-api-key")
            seen["version"] = request.headers.get("anthropic-version")
            return httpx.Response(200, json=ANTHROPIC_MODELS_BODY, request=request)

        adapter = AnthropicAdapter()
        async with _client(handler) as client:
            models = await adapter.list_models("https://api.anthropic.test", "sk-ant", client=client)
        assert [m.id for m in models] == ["claude-sonnet-4-6", "claude-haiku-4-5"]
        assert seen["url"] == "https://api.anthropic.test/v1/models"
        assert seen["key"] == "sk-ant" and seen["version"] == "2023-06-01"

    def test_build_and_parse_chat(self):
        adapter = AnthropicAdapter()
        req = adapter.build_chat(
            "https://api.anthropic.test", "sk-ant", "claude-sonnet-4-6",
            [{"role": "user", "content": "ping"}], max_tokens=1,
        )
        assert req.url == "https://api.anthropic.test/v1/messages"
        assert req.headers["x-api-key"] == "sk-ant"
        assert req.json_payload["max_tokens"] == 1
        assert adapter.parse_chat({"content": [{"type": "text", "text": "pong"}]}) == "pong"


class TestGoogleGemini:
    @pytest.mark.asyncio
    async def test_list_models_filters_generate_content_and_strips_prefix(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["key"] = request.headers.get("x-goog-api-key")
            return httpx.Response(200, json=GEMINI_MODELS_BODY, request=request)

        adapter = GoogleGeminiAdapter()
        async with _client(handler) as client:
            models = await adapter.list_models(
                "https://gemini.test", "goog-key", client=client
            )
        assert [m.id for m in models] == ["gemini-2.5-flash", "gemini-2.5-pro"]  # embedding 被过滤 + 前缀剥离
        assert seen["url"] == "https://gemini.test/v1beta/models"
        assert seen["key"] == "goog-key"

    def test_build_and_parse_chat(self):
        adapter = GoogleGeminiAdapter()
        req = adapter.build_chat(
            "https://gemini.test", "goog-key", "gemini-2.5-flash",
            [{"role": "user", "content": "ping"}], max_tokens=1,
        )
        assert req.url == "https://gemini.test/v1beta/models/gemini-2.5-flash:generateContent"
        assert req.headers["x-goog-api-key"] == "goog-key"
        assert req.json_payload["contents"][0]["parts"][0]["text"] == "ping"
        assert req.json_payload["generationConfig"]["maxOutputTokens"] == 1
        assert adapter.parse_chat(
            {"candidates": [{"content": {"parts": [{"text": "pong"}]}}]}
        ) == "pong"


class TestErrorMasking:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("adapter_cls", [OpenAICompatibleAdapter, AnthropicAdapter, GoogleGeminiAdapter])
    async def test_error_masks_response_body(self, adapter_cls):
        secret = "SK-LEAKED-KEY-INSIDE-BODY"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text=f"unauthorized {secret}", request=request)

        adapter = adapter_cls()
        async with _client(handler) as client:
            with pytest.raises(ProtocolError) as exc_info:
                await adapter.list_models("https://api.test", "k", client=client)
        assert "401" in str(exc_info.value)
        assert secret not in str(exc_info.value)


class TestRegistry:
    def test_get_adapter_by_type(self):
        assert get_adapter("openai_compatible").type_id == "openai_compatible"
        assert get_adapter("anthropic").type_id == "anthropic"
        assert get_adapter("google_gemini").type_id == "google_gemini"
        with pytest.raises(KeyError):
            get_adapter("azure")

    @pytest.mark.parametrize(
        "model_id,expected",
        [
            ("gpt-4o", True), ("claude-sonnet-4-6", True), ("gemini-2.5-flash", True),
            ("text-embedding-3-small", False), ("whisper-1", False), ("tts-1", False),
            ("rerank-v2", False), ("dall-e-3", False), ("omni-moderation-latest", False),
        ],
    )
    def test_is_chat_model_keywords(self, model_id, expected):
        assert get_adapter("openai_compatible").is_chat_model(model_id) is expected
