"""LiteLLM 治理封装（L2/L3）：Key CRUD + 新租户虚拟键，全走 Admin API。"""
from typing import Any, Optional

from config import settings
from backend.services.litellm.admin_client import LiteLlmAdminClient
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger
from platform_core.schemas.litellm import LitellmKeyCreate, LitellmKeyOut

logger = get_logger("service.litellm.admin")


class LiteLlmAdminService:
    def __init__(self, client: Optional[LiteLlmAdminClient] = None):
        self.client = client or LiteLlmAdminClient()

    def _require_enabled(self) -> None:
        if not settings.get("LITELLM.ADMIN.ENABLED", False):
            raise BusinessException("LiteLLM Admin 未启用")

    async def list_keys(self) -> list[dict[str, Any]]:
        logger.info("列出 LiteLLM 虚拟键")
        self._require_enabled()
        data = await self.client.list_keys()
        keys = data.get("keys") or data.get("data") or []
        return keys if isinstance(keys, list) else []

    async def create_key(self, payload: LitellmKeyCreate) -> LitellmKeyOut:
        logger.info(f"签发 LiteLLM 虚拟键 | alias={payload.key_alias}")
        self._require_enabled()
        body: dict[str, Any] = {"key_alias": payload.key_alias}
        if payload.max_budget is not None:
            body["max_budget"] = payload.max_budget
        if payload.metadata:
            body["metadata"] = payload.metadata
        raw = await self.client.generate_key(body)
        return LitellmKeyOut(
            key_alias=raw.get("key_alias") or payload.key_alias,
            token=raw.get("key") or raw.get("token"),
            max_budget=raw.get("max_budget", payload.max_budget),
            spend=raw.get("spend"),
            raw=raw,
        )

    async def delete_key(self, key: str) -> None:
        logger.info("删除 LiteLLM 虚拟键")
        self._require_enabled()
        await self.client.delete_key(key)

    async def spend_logs(self) -> list[dict[str, Any]]:
        logger.info("读取 LiteLLM spend")
        self._require_enabled()
        data = await self.client.spend_logs()
        logs = data.get("data") or data.get("logs") or []
        return logs if isinstance(logs, list) else [data] if data else []

    async def ensure_tenant_key(self, tenant_id: int) -> None:
        logger.info(f"确保租户虚拟键 | tenant={tenant_id}")
        if not settings.get("LITELLM.ADMIN.ENABLED", False):
            return
        await self.client.generate_key({
            "key_alias": f"tenant:{tenant_id}",
            "metadata": {"tenant_id": tenant_id},
        })
