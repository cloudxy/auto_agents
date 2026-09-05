"""三协议适配器实现（方案 B · B-M1-1）

请求映射与总方案 §6.1 一致：
- openai_compatible：GET {base}/models（Bearer）；POST {base}/chat/completions
- anthropic：GET {base}/v1/models（x-api-key + anthropic-version）；POST {base}/v1/messages
- google_gemini：GET {base}/v1beta/models（x-goog-api-key，按 generateContent 过滤并剥
  models/ 前缀）；POST {base}/v1beta/models/{model}:generateContent
"""
import httpx
from typing import Optional

from backend.services.llm_protocol.base import (
    ChatRequest, ModelInfo, ModelList, execute_json,
)

# 非对话模型关键字表（可由调用方覆盖；总方案 §6.1 默认集）
CHAT_MODEL_EXCLUDE_KEYWORDS = (
    "embedding", "tts", "whisper", "rerank", "dall-e",
    "image", "audio", "moderation", "guard",
)


def _default_chat_filter(model_id: str) -> bool:
    lowered = model_id.lower()
    return not any(kw in lowered for kw in CHAT_MODEL_EXCLUDE_KEYWORDS)


class OpenAICompatibleAdapter:
    """OpenAI 兼容协议（OpenAI/DeepSeek/通义/智谱/Kimi/OpenRouter/硅基/Groq/Ollama/中转站…）"""

    type_id = "openai_compatible"
    display_name = "OpenAI 兼容"

    async def list_models(
        self, base_url: str, api_key: str, client: Optional[httpx.AsyncClient] = None
    ) -> ModelList:
        data = await execute_json(
            client, "GET", f"{base_url.rstrip('/')}/models",
            {"Authorization": f"Bearer {api_key}"},
        )
        models = [
            ModelInfo(str(item.get("id") or ""), str(item.get("owned_by") or ""))
            for item in data.get("data") or []
        ]
        return ModelList([m for m in models if m.id], _default_chat_filter)

    def build_chat(
        self, base_url: str, api_key: str, model: str,
        messages: list[dict], max_tokens: int = 1,
    ) -> ChatRequest:
        return ChatRequest(
            url=f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json_payload={"model": model, "messages": messages, "max_tokens": max_tokens},
        )

    def parse_chat(self, resp_json: dict) -> str:
        message = ((resp_json.get("choices") or [{}])[0].get("message")) or {}
        content = message.get("content")
        if not content:
            # reasoning 模型（max_tokens 极小时 content 常为空，思考字段有产出）：
            # DeepSeek-R1 风格 reasoning_content / 部分兼容网关 reasoning，连通即视为有响应
            content = message.get("reasoning_content") or message.get("reasoning")
        return str(content or "")

    def is_chat_model(self, model_id: str) -> bool:
        return _default_chat_filter(model_id)

    def chat_only(self, models: ModelList) -> ModelList:
        return models.chat_only()


class AnthropicAdapter:
    """Anthropic 原生协议"""

    type_id = "anthropic"
    display_name = "Anthropic 原生"

    _HEADERS_BASE = {"anthropic-version": "2023-06-01", "Content-Type": "application/json"}

    async def list_models(
        self, base_url: str, api_key: str, client: Optional[httpx.AsyncClient] = None
    ) -> ModelList:
        data = await execute_json(
            client, "GET", f"{base_url.rstrip('/')}/v1/models",
            {"x-api-key": api_key, **self._HEADERS_BASE},
        )
        models = [
            ModelInfo(str(item.get("id") or ""), "anthropic", str(item.get("display_name") or ""))
            for item in data.get("data") or []
        ]
        return ModelList([m for m in models if m.id], _default_chat_filter)

    def build_chat(
        self, base_url: str, api_key: str, model: str,
        messages: list[dict], max_tokens: int = 1,
    ) -> ChatRequest:
        return ChatRequest(
            url=f"{base_url.rstrip('/')}/v1/messages",
            headers={"x-api-key": api_key, **self._HEADERS_BASE},
            json_payload={"model": model, "max_tokens": max_tokens, "messages": messages},
        )

    def parse_chat(self, resp_json: dict) -> str:
        blocks = resp_json.get("content") or []
        texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
        return "".join(t for t in texts if t)

    def is_chat_model(self, model_id: str) -> bool:
        return _default_chat_filter(model_id)

    def chat_only(self, models: ModelList) -> ModelList:
        return models.chat_only()


class GoogleGeminiAdapter:
    """Google Gemini 原生协议（v1beta）"""

    type_id = "google_gemini"
    display_name = "Google Gemini"

    async def list_models(
        self, base_url: str, api_key: str, client: Optional[httpx.AsyncClient] = None
    ) -> ModelList:
        data = await execute_json(
            client, "GET", f"{base_url.rstrip('/')}/v1beta/models",
            {"x-goog-api-key": api_key},
        )
        models: list[ModelInfo] = []
        for item in data.get("models") or []:
            methods = item.get("supportedGenerationMethods") or []
            if "generateContent" not in methods:
                continue
            raw_name = str(item.get("name") or "")
            model_id = raw_name.removeprefix("models/").strip()
            if model_id:
                models.append(ModelInfo(model_id, "google", raw_name))
        return ModelList(models, _default_chat_filter)

    def build_chat(
        self, base_url: str, api_key: str, model: str,
        messages: list[dict], max_tokens: int = 1,
    ) -> ChatRequest:
        contents = [
            {"role": msg.get("role", "user"), "parts": [{"text": msg.get("content", "")}]}
            for msg in messages
        ]
        return ChatRequest(
            url=f"{base_url.rstrip('/')}/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json_payload={
                "contents": contents,
                "generationConfig": {"maxOutputTokens": max_tokens},
            },
        )

    def parse_chat(self, resp_json: dict) -> str:
        candidate = (resp_json.get("candidates") or [{}])[0]
        parts = ((candidate.get("content") or {}).get("parts")) or []
        return "".join(str(p.get("text") or "") for p in parts)

    def is_chat_model(self, model_id: str) -> bool:
        return _default_chat_filter(model_id)

    def chat_only(self, models: ModelList) -> ModelList:
        return models.chat_only()


_ADAPTERS = {
    cls.type_id: cls()
    for cls in (OpenAICompatibleAdapter, AnthropicAdapter, GoogleGeminiAdapter)
}


def get_adapter(provider_type: str):
    """按协议类型取适配器（未注册类型 KeyError）"""
    return _ADAPTERS[provider_type]
