"""LiteLLM 数据面：POST /v1/chat/completions；空模型预检 GET /v1/models。

backend 只持虚拟 Key（``LITELLM.MASTER_KEY``）。禁止 DSN / 上游 Key。
禁止 import admin。GET /v1/models 是 OpenAI 数据面，不是值班 admin。
"""
from typing import Any, Optional

import httpx

from backend.services.llm_gateway._settings import _http_json
from platform_core.logger import get_logger

logger = get_logger("api")

_CHAT_PATH = "/v1/chat/completions"
_MODELS_PATH = "/v1/models"


async def chat_completions(
    body: dict[str, Any],
    *,
    timeout: Optional[float] = None,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> dict[str, Any]:
    logger.info(f"LiteLLM POST {_CHAT_PATH} model={body.get('model')}")
    data = await _http_json(
        "POST", _CHAT_PATH, json_body=body, timeout=timeout, transport=transport,
    )
    return data if isinstance(data, dict) else {"data": data}


async def list_v1_models(
    *,
    timeout: Optional[float] = None,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> list[str]:
    logger.info(f"LiteLLM GET {_MODELS_PATH}")
    data = await _http_json("GET", _MODELS_PATH, timeout=timeout, transport=transport)
    if isinstance(data, dict):
        raw = data.get("data") or data.get("models") or []
    elif isinstance(data, list):
        raw = data
    else:
        raw = []
    models: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            mid = item.get("id") or item.get("model_name") or item.get("model")
            if mid:
                models.append(str(mid))
        elif item:
            models.append(str(item))
    return models
