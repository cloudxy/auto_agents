"""new-api 管理 API 轻客户端（阶段三共享：渠道调度器 + 真伪探针）

职责：
- 管理面：渠道分页列表 / 单渠道详情 / 启停渠道（PUT /api/channel/，蓝本 :158-184 请求写法）
- 采集面：POST {BASE_URL}/v1/chat/completions（探针行为指纹采集）

安全与约定：
- BASE_URL / ACCESS_TOKEN 全部来自配置（NEWAPI.*），不硬编码（红线 R1）
- trust_env=False 与 notify_service 同款：规避本机代理（Clash 等）劫持 httpx 请求
- new-api 渠道状态语义（model/channel.go）：1=启用 2=人工禁用 3=自动禁用；
  调度器禁用固定用 3（auto disabled），与人工禁用 2 天然区分，
  冷却恢复时可凭状态识别人工操作（不覆盖人工决策）
- 所有方法失败返回 None/False/ok=False 并记日志，不向上抛（调用方按渠道隔离）
"""
import time
from typing import Final, Optional

import httpx

from config import settings
from platform_core.logger import get_logger

logger = get_logger("api")

# new-api 渠道状态值（与 new-api model/channel.go 语义对齐）
CHANNEL_STATUS_ENABLED: Final[int] = 1
CHANNEL_STATUS_MANUALLY_DISABLED: Final[int] = 2
CHANNEL_STATUS_AUTO_DISABLED: Final[int] = 3

# Redis 键命名空间（调度器与探针同前缀不同锁名；渠道级配置/状态 hash）
NEWAPI_SCHEDULER_LOCK_KEY: Final[str] = "newapi:scheduler:lock"
NEWAPI_PROBE_LOCK_KEY: Final[str] = "newapi:probe:lock"
NEWAPI_CHANNEL_CFG_PREFIX: Final[str] = "newapi:channel:cfg:"
NEWAPI_CHANNEL_STATE_PREFIX: Final[str] = "newapi:scheduler:state:"

# 管理面单请求超时（秒）
DEFAULT_API_TIMEOUT: Final[float] = 15.0
# 采集面单请求超时（秒）
DEFAULT_CHAT_TIMEOUT: Final[float] = 60.0


def _main_async_session():
    """主库（backend 自身 DB）AsyncSession —— 与 new-api 库独立 engine 完全隔离

    渠道事件/探针结果落本库 channel_events / channel_probe_results 表，
    new-api 库只读（logs 聚合），两侧连接互不共享。
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    from platform_core.db import get_manager

    return AsyncSession(get_manager().async_engines["DEFAULT"])


class NewapiApiClient:
    """new-api HTTP 客户端（管理面 + 采集面；失败静默返回，不抛异常）"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = DEFAULT_API_TIMEOUT,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.base_url = str(
            base_url if base_url is not None else settings.get("NEWAPI.BASE_URL", "")
        ).rstrip("/")
        self.token = str(
            token if token is not None else settings.get("NEWAPI.ACCESS_TOKEN", "") or ""
        )
        self.timeout = timeout
        # transport 仅供测试注入 MockTransport，生产恒为 None
        self._transport = transport

    @property
    def _admin_headers(self) -> dict:
        """管理面请求头：Authorization Bearer + New-Api-User（新版 new-api 必需）"""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        user_id = str(settings.get("NEWAPI.ADMIN_USER_ID", "") or "")
        if user_id:
            headers["New-Api-User"] = user_id
        return headers

    async def list_channels(self) -> list[dict]:
        """分页拉取全量渠道（含禁用，status=all；对齐蓝本 list_channels 写法）"""
        items: list[dict] = []
        try:
            async with httpx.AsyncClient(
                trust_env=False, timeout=self.timeout, transport=self._transport
            ) as client:
                page = 1
                while True:
                    resp = await client.get(
                        f"{self.base_url}/api/channel/",
                        params={"p": page, "page_size": 100, "status": "all"},
                        headers=self._admin_headers,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    batch = (data.get("data") or {}).get("items") or []
                    items.extend(batch)
                    if len(batch) < 100:
                        break
                    page += 1
        except Exception as e:  # noqa: BLE001
            logger.error(f"拉取渠道列表失败: base_url={self.base_url}, error={e}")
            return []
        return items

    async def get_channel(self, channel_id: int) -> Optional[dict]:
        """单渠道详情（冷却恢复前核对当前状态，防覆盖人工操作）"""
        try:
            async with httpx.AsyncClient(
                trust_env=False, timeout=self.timeout, transport=self._transport
            ) as client:
                resp = await client.get(
                    f"{self.base_url}/api/channel/{channel_id}",
                    headers=self._admin_headers,
                )
                resp.raise_for_status()
                data = resp.json()
            if not data.get("success"):
                logger.warning(
                    f"获取渠道详情被拒绝: channel_id={channel_id}, message={data.get('message')}"
                )
                return None
            return data.get("data") or None
        except Exception as e:  # noqa: BLE001
            logger.warning(f"获取渠道详情失败: channel_id={channel_id}, error={e}")
            return None

    async def set_channel_status(self, channel_id: int, status: int) -> bool:
        """启停渠道：PUT /api/channel/ body={"id":..,"status":..}（蓝本 :158-184 写法）

        status 取值见模块头注释（1 启用 / 2 人工禁用 / 3 自动禁用）。
        """
        try:
            async with httpx.AsyncClient(
                trust_env=False, timeout=self.timeout, transport=self._transport
            ) as client:
                resp = await client.put(
                    f"{self.base_url}/api/channel/",
                    json={"id": channel_id, "status": status},
                    headers=self._admin_headers,
                )
                resp.raise_for_status()
                data = resp.json()
            if not data.get("success"):
                logger.warning(
                    f"渠道状态更新被拒绝: channel_id={channel_id}, status={status}, "
                    f"message={data.get('message')}"
                )
                return False
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(
                f"渠道状态更新失败: channel_id={channel_id}, status={status}, error={e}"
            )
            return False

    async def chat_completion(
        self, model: str, prompt: str, timeout: float = DEFAULT_CHAT_TIMEOUT
    ) -> dict:
        """POST /v1/chat/completions 采集探针响应（非流式单轮）

        鉴权：PROBE_API_KEY 优先（sk- 中转令牌），未配置回退 ACCESS_TOKEN。
        返回统一结构（永不抛异常）：
        {"ok", "content", "latency_ms", "usage", "model", "reasoning_tokens", "error"}
        """
        api_key = str(settings.get("NEWAPI.PROBE_API_KEY", "") or "") or self.token
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(
                trust_env=False, timeout=timeout, transport=self._transport
            ) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                )
            latency_ms = int((time.monotonic() - started) * 1000)
            if resp.status_code >= 400:
                return _failed_chat(model, latency_ms, f"http {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            choice = (data.get("choices") or [{}])[0]
            content = str(((choice.get("message") or {}).get("content") or "")).strip()
            usage = data.get("usage") or {}
            reasoning = int(
                (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
            )
            return {
                "ok": bool(content),
                "content": content,
                "latency_ms": latency_ms,
                "usage": usage,
                "model": str(data.get("model") or model),
                "reasoning_tokens": reasoning,
                "error": None if content else "empty content",
            }
        except Exception as e:  # noqa: BLE001
            latency_ms = int((time.monotonic() - started) * 1000)
            return _failed_chat(model, latency_ms, str(e))


def _failed_chat(model: str, latency_ms: int, error: str) -> dict:
    """chat_completion 失败统一返回结构"""
    return {
        "ok": False,
        "content": "",
        "latency_ms": latency_ms,
        "usage": {},
        "model": model,
        "reasoning_tokens": 0,
        "error": error,
    }
