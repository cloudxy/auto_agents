"""LLM 共享 AsyncClient 缓存（provider 路径专用；兜底路径保持现状的一次性 client）

拆分自 llm_client.py（规模治理，行为零变化）：连接池常量、缓存键、
get_shared_client / invalidate_client_cache。llm_client 原样 re-export 全部名字
（含两张缓存字典的同一对象），门面 ai_planner_service 的 import / patch 路径不变。

本模块是叶子：不 import 门面、不 import llm_gateway，也不读 seam。
httpx 为全局共享模块对象（patch httpx.AsyncClient 即全局生效）。
"""
import hashlib
from typing import Optional

import httpx

from platform_core.logger import get_logger

logger = get_logger("api")

# key=(base_url, sha256(api_key)[:12])：Authorization 头在创建时固化，密钥轮换
# 自然产生新条目；owner 记录归属供应商，热切换/变更/删除时由 invalidate 定向关闭
_HTTP_CLIENTS: dict[tuple[str, str], httpx.AsyncClient] = {}
_HTTP_CLIENT_OWNER: dict[tuple[str, str], int] = {}
# 连接池与超时拆分：connect 上限 10s，读/写/取池跟随调用方超时
_CLIENT_MAX_CONNECTIONS = 20
_CLIENT_MAX_KEEPALIVE_CONNECTIONS = 10
_CLIENT_KEEPALIVE_EXPIRY = 30.0
_CLIENT_CONNECT_TIMEOUT = 10.0


def _client_cache_key(base_url: str, api_key: str) -> tuple[str, str]:
    """共享 client 缓存键：base_url + 密钥指纹（明文/完整哈希均不落内存键）"""
    return (base_url.rstrip("/"), hashlib.sha256((api_key or "").encode("utf-8")).hexdigest()[:12])


async def get_shared_client(base_url: str, api_key: str, timeout: float, provider_id: Optional[int] = None) -> httpx.AsyncClient:
    logger.debug(f"获取共享 LLM client: provider_id={provider_id}, timeout={timeout}")
    # 取（或建）共享 AsyncClient：连接池复用，Limits + connect/read 超时拆分
    key = _client_cache_key(base_url, api_key)
    client = _HTTP_CLIENTS.get(key)
    if client is not None and not client.is_closed:
        return client
    if client is not None:  # 已被外部关闭的残留条目
        _HTTP_CLIENTS.pop(key, None)
        _HTTP_CLIENT_OWNER.pop(key, None)
    limits = httpx.Limits(
        max_connections=_CLIENT_MAX_CONNECTIONS,
        max_keepalive_connections=_CLIENT_MAX_KEEPALIVE_CONNECTIONS,
        keepalive_expiry=_CLIENT_KEEPALIVE_EXPIRY,
    )
    timeout_cfg = httpx.Timeout(
        timeout,
        connect=min(_CLIENT_CONNECT_TIMEOUT, timeout),
        read=timeout, write=timeout, pool=timeout,
    )
    # trust_env=False：不读环境变量与系统代理（对齐 notify/newapi/llm_provider 约定，
    # 规避本机代理软件如 Clash 劫持 httpx 请求返回 502 的陷阱）
    client = httpx.AsyncClient(
        timeout=timeout_cfg, limits=limits, follow_redirects=False, trust_env=False,
    )
    _HTTP_CLIENTS[key] = client
    if provider_id is not None:
        _HTTP_CLIENT_OWNER[key] = provider_id
    return client


async def invalidate_client_cache(provider_id: Optional[int] = None) -> None:
    logger.debug(f"失效共享 LLM client 缓存: provider_id={provider_id}")
    # 失效共享 client 缓存：provider_id 定向清理该供应商的连接，None 全清。
    # 须在事件循环内 await 调用（供应商变更/热切换/删除后由 Service 层触发）；
    # 飞行中的请求不受影响，下次重试自动建新 client。
    keys = [k for k, owner in _HTTP_CLIENT_OWNER.items()
            if provider_id is None or owner == provider_id]
    for key in keys:
        client = _HTTP_CLIENTS.pop(key, None)
        _HTTP_CLIENT_OWNER.pop(key, None)
        if client is None:
            continue
        try:
            await client.aclose()
        except Exception as e:  # noqa: BLE001 关闭失败仅记日志，不影响主流程
            logger.warning(f"共享 LLM client 关闭失败（忽略）: {e}")
