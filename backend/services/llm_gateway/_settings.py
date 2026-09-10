"""LiteLLM HTTP 连接键：backend 只持虚拟 Key，禁止网关库 DSN。"""
from typing import Any, Optional

import httpx

from backend.config_consts import LITELLM_BASE_URL, LITELLM_TIMEOUT
from config import settings

_JSON_HEADERS = {"Content-Type": "application/json"}


def _base_url() -> str:
    return str(settings.get("LITELLM.BASE_URL", LITELLM_BASE_URL) or "").rstrip("/")


def _timeout_sec() -> float:
    return float(settings.get("LITELLM.TIMEOUT", LITELLM_TIMEOUT) or LITELLM_TIMEOUT)


def _virtual_key() -> str:
    return str(settings.get("LITELLM.MASTER_KEY", "") or "")


def _auth_headers() -> dict[str, str]:
    headers = dict(_JSON_HEADERS)
    key = _virtual_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


async def _http_json(
    method: str,
    path: str,
    *,
    json_body: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
    timeout: Optional[float] = None,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Any:
    url = f"{_base_url()}{path}"
    sec = timeout if timeout is not None else _timeout_sec()
    async with httpx.AsyncClient(
        trust_env=False, timeout=sec, transport=transport, follow_redirects=False,
    ) as client:
        resp = await client.request(
            method, url, json=json_body, params=params, headers=_auth_headers(),
        )
        resp.raise_for_status()
        if not resp.content:
            return {}
        return resp.json()
