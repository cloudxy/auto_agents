"""new-api 管理 API 轻客户端（阶段三共享：渠道调度器 + 真伪探针）

职责：
- 管理面：渠道分页列表 / 单渠道详情 / 启停渠道（PUT /api/channel/，蓝本 :158-184 请求写法）
- 采集面：POST {BASE_URL}/v1/chat/completions（探针行为指纹采集）

安全与约定：
- T-20：本客户端不再读 NEWAPI.*；调用方必须显式传入 base_url / token
- trust_env=False 与 notify_service 同款：规避本机代理（Clash 等）劫持 httpx 请求
- new-api 渠道状态语义（model/channel.go）：1=启用 2=人工禁用 3=自动禁用；
  调度器禁用固定用 3（auto disabled），与人工禁用 2 天然区分，
  冷却恢复时可凭状态识别人工操作（不覆盖人工决策）
- 所有方法失败返回 None/False/ok=False 并记日志，不向上抛（调用方按渠道隔离）
"""
import hashlib
import json
import time
from typing import Final, Optional

import httpx

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
# SH-06 expand：HTTP/Redis 用 string gateway_ref；写只落 relay: 前缀
RELAY_CHANNEL_CFG_PREFIX: Final[str] = "relay:channel:cfg:"
NEWAPI_CHANNEL_STATE_PREFIX: Final[str] = "newapi:scheduler:state:"
# SH-06：冷却状态新写只落 relay:；双读仍先旧 newapi:scheduler:state:
RELAY_CHANNEL_STATE_PREFIX: Final[str] = "relay:channel:state:"

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
        probe_api_key: Optional[str] = None,
        admin_user_id: str = "",
    ):
        self.base_url = str(base_url or "").rstrip("/")
        self.token = str(token or "")
        self.timeout = timeout
        self._probe_api_key = str(probe_api_key or "")
        self._admin_user_id = str(admin_user_id or "")
        # transport 仅供测试注入 MockTransport，生产恒为 None
        self._transport = transport

    @property
    def _admin_headers(self) -> dict:
        """管理面请求头：Authorization Bearer + New-Api-User（新版 new-api 必需）"""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self._admin_user_id:
            headers["New-Api-User"] = self._admin_user_id
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
        api_key = self._probe_api_key or self.token
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


def cfg_redis_keys(channel_id: int | str | None, gateway_ref: str | None) -> list[str]:
    """SH-06 双读顺序：newapi:channel:cfg:{id} → relay:channel:cfg:{ref}。"""
    logger.debug(f"构造渠道配置键: channel_id={channel_id}, gateway_ref={gateway_ref}")
    keys: list[str] = []
    if channel_id is not None:
        keys.append(f"{NEWAPI_CHANNEL_CFG_PREFIX}{channel_id}")
    ref = gateway_ref if gateway_ref is not None else (
        str(channel_id) if channel_id is not None else None
    )
    if ref is not None:
        keys.append(f"{NEWAPI_CHANNEL_CFG_PREFIX}{ref}")
        keys.append(f"{RELAY_CHANNEL_CFG_PREFIX}{ref}")
    out: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


async def read_cfg_hash(
    redis, *, channel_id: int | str | None = None, gateway_ref: str | None = None,
) -> dict:
    """双读：旧 int 键优先，未命中再读 relay string ref。"""
    logger.debug(f"双读渠道配置: channel_id={channel_id}, gateway_ref={gateway_ref}")
    for key in cfg_redis_keys(channel_id, gateway_ref):
        raw = await redis.hgetall(key)
        if raw:
            return raw
    return {}


async def write_cfg_hash(
    redis, mapping: dict, *, channel_id: int | str | None = None,
    gateway_ref: str | None = None,
) -> str:
    """新写只落 relay:channel:cfg:{ref}（禁止第三 Redis 前缀）。"""
    logger.info(f"写入 relay 渠道配置: channel_id={channel_id}, gateway_ref={gateway_ref}")
    ref = gateway_ref if gateway_ref is not None else str(channel_id)
    key = f"{RELAY_CHANNEL_CFG_PREFIX}{ref}"
    await redis.hset(key, mapping=mapping)
    return key


async def delete_cfg_hash(
    redis, *, channel_id: int | str | None = None, gateway_ref: str | None = None,
) -> None:
    """expand 清除：旧键与 relay 键都删。"""
    logger.info(f"清除渠道配置键: channel_id={channel_id}, gateway_ref={gateway_ref}")
    keys = cfg_redis_keys(channel_id, gateway_ref)
    if keys:
        await redis.delete(*keys)


def _channel_id_from_ref(gateway_ref: str) -> int:
    """string gateway_ref → BIGINT channel_id（不改列类型、不加表列）。"""
    logger.debug(f"gateway_ref 映射 channel_id: {gateway_ref}")
    text = str(gateway_ref or "").strip()
    if text.isdigit():
        value = int(text)
        if value > 0:
            return value
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % (2**63 - 1) or 1


def _cfg_manual_disabled(raw: dict | None) -> bool:
    """人工禁用只读 Redis cfg（不改 schema）。"""
    logger.debug("检查人工禁用标记")
    if not raw:
        return False
    val = str(raw.get("manual_disabled") or raw.get("disabled") or "").strip().lower()
    return val in {"1", "true", "yes"}


def state_redis_keys(
    channel_id: int | str | None, gateway_ref: str | None,
) -> list[str]:
    """SH-06 状态双读：newapi:scheduler:state:{id} → relay:channel:state:{ref}。"""
    logger.debug(f"构造调度状态键: channel_id={channel_id}, gateway_ref={gateway_ref}")
    keys: list[str] = []
    if channel_id is not None:
        keys.append(f"{NEWAPI_CHANNEL_STATE_PREFIX}{channel_id}")
    ref = gateway_ref if gateway_ref is not None else (
        str(channel_id) if channel_id is not None else None
    )
    if ref is not None:
        keys.append(f"{NEWAPI_CHANNEL_STATE_PREFIX}{ref}")
        keys.append(f"{RELAY_CHANNEL_STATE_PREFIX}{ref}")
    out: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


async def read_state_json(
    redis, *, channel_id: int | str | None = None, gateway_ref: str | None = None,
) -> dict:
    """双读调度状态 JSON；未命中返回空 dict。"""
    logger.debug(f"双读调度状态: channel_id={channel_id}, gateway_ref={gateway_ref}")
    for key in state_redis_keys(channel_id, gateway_ref):
        raw = await redis.get(key)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return {}


async def write_state_json(
    redis, state: dict, *, channel_id: int | str | None = None,
    gateway_ref: str | None = None,
) -> str:
    """新写只落 relay:channel:state:{ref}；清旧键以免双读被挡住。"""
    logger.info(f"写入 relay 调度状态: channel_id={channel_id}, gateway_ref={gateway_ref}")
    ref = gateway_ref if gateway_ref is not None else str(channel_id)
    old = [
        key for key in state_redis_keys(channel_id, gateway_ref)
        if not key.startswith(RELAY_CHANNEL_STATE_PREFIX)
    ]
    if old:
        await redis.delete(*old)
    key = f"{RELAY_CHANNEL_STATE_PREFIX}{ref}"
    await redis.set(key, json.dumps(state, ensure_ascii=False))
    return key


async def delete_state_json(
    redis, *, channel_id: int | str | None = None, gateway_ref: str | None = None,
) -> None:
    """expand 清除：旧状态键与 relay 状态键都删。"""
    logger.info(f"清除调度状态键: channel_id={channel_id}, gateway_ref={gateway_ref}")
    keys = state_redis_keys(channel_id, gateway_ref)
    if keys:
        await redis.delete(*keys)


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
