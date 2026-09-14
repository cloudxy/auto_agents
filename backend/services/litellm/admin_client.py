"""LiteLLM Admin HTTP 客户端（L2：禁直连其库 / 禁 SDK）。"""
from typing import Any, Optional

import httpx

from config import settings
from platform_core.logger import get_logger

logger = get_logger("service.litellm.admin")

_DEFAULT_TIMEOUT = 15.0


class LiteLlmAdminClient:
    """只走 HTTP Admin API；失败返回空结构，由 Service 决定是否上抛。"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        master_key: Optional[str] = None,
        timeout: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.base_url = str(
            base_url if base_url is not None else settings.get("LITELLM.ADMIN.BASE_URL", "")
            or ""
        ).rstrip("/")
        self.master_key = str(
            master_key if master_key is not None
            else settings.get("LITELLM.ADMIN.MASTER_KEY", "") or ""
        )
        self.timeout = float(
            timeout if timeout is not None
            else settings.get("LITELLM.ADMIN.TIMEOUT_SECONDS", _DEFAULT_TIMEOUT)
            or _DEFAULT_TIMEOUT
        )
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.master_key:
            headers["Authorization"] = f"Bearer {self.master_key}"
        return headers

    def _client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {"timeout": self.timeout, "trust_env": False}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def generate_key(self, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info("LiteLLM 签发虚拟键")
        return await self._post("/key/generate", payload)

    async def list_keys(self) -> dict[str, Any]:
        logger.info("LiteLLM 列出虚拟键")
        return await self._get("/key/list")

    async def delete_key(self, key: str) -> dict[str, Any]:
        logger.info("LiteLLM 删除虚拟键")
        return await self._post("/key/delete", {"keys": [key]})

    async def spend_logs(self) -> dict[str, Any]:
        logger.info("LiteLLM 读取 spend")
        return await self._get("/spend/logs")

    async def _get(self, path: str) -> dict[str, Any]:
        if not self.base_url:
            return {}
        async with self._client() as client:
            resp = await client.get(f"{self.base_url}{path}", headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"data": data}

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.base_url:
            return {}
        async with self._client() as client:
            resp = await client.post(
                f"{self.base_url}{path}", headers=self._headers(), json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"data": data}
