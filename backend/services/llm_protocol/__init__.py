"""LLM 协议适配层（方案 B · B-M1-1）

统一接口（list_models / build_chat / parse_chat / is_chat_model）覆盖三协议：
openai_compatible / anthropic / google_gemini。全部外呼 trust_env=False，
错误只回状态码 + reason（脱敏），key 不落日志。
"""
from backend.services.llm_protocol.adapters import (
    CHAT_MODEL_EXCLUDE_KEYWORDS,
    AnthropicAdapter,
    GoogleGeminiAdapter,
    OpenAICompatibleAdapter,
    get_adapter,
)
from backend.services.llm_protocol.base import (
    ChatRequest,
    ModelInfo,
    ModelList,
    ProtocolError,
    execute_json,
)

__all__ = [
    "AnthropicAdapter",
    "GoogleGeminiAdapter",
    "OpenAICompatibleAdapter",
    "get_adapter",
    "ProtocolError",
    "ModelInfo",
    "ModelList",
    "ChatRequest",
    "execute_json",
    "CHAT_MODEL_EXCLUDE_KEYWORDS",
]
