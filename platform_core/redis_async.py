"""异步 Redis 门面 - asyncio redis 客户端统一创建/复用（Backend 侧 async 上下文专用）

背景：backend/services 与 API 层此前大量直调同步 redis_client()（网络 IO 阻塞事件循环）。
本模块提供与同步门面 platform_core.db.redis_client 取用方式对齐的 get_async_redis()：
- 连接串来源：config 注入的 REDIS.<KEY>.URL（密码取法与 db.py 对齐，
  兼容环境变量 REDIS_<KEY>_PASSWORD > .env 扁平键 > yml 嵌套占位值）
- 生产态：进程级缓存客户端实例（连接池复用，max_connections 对齐同步池 100）
- 测试态（pytest）：每次调用新建实例 —— pytest 每测试/每请求独立事件循环，
  缓存复用会报 "attached to a different loop"（与 db.py NullPool 处理同一陷阱）

使用约定：
- 返回客户端的方法均为协程：await client.get(key) / await client.rpush(...)
- 调用方禁止 close 缓存实例（生产态为进程级共享）；消费者等需独占生命周期的
  组件应自建连接（与现有 5 处 aioredis.from_url 用法一致）
"""
import sys
from typing import Dict, Optional

import redis.asyncio as aioredis

from config import settings

# 测试态判定（与 platform_core.db 同一陷阱、同一处理策略）
_IN_PYTEST = "pytest" in sys.modules

# 生产态进程级缓存：key -> asyncio redis 客户端（连接池复用）
_clients: Dict[str, aioredis.Redis] = {}


def _resolve_url(key: str) -> str:
    """解析实例连接串

    正常路径：config/__init__.py 启动时已注入 REDIS.<KEY>.URL（含密码多层取法）；
    兜底路径：URL 缺失时按 HOST/PORT/DB 拼接（无密码场景，与 db.py 同构）。
    """
    url = settings.get(f"REDIS.{key}.URL", "")
    if url:
        return str(url)
    redis_cfg = getattr(settings, "REDIS", {})
    cfg = getattr(redis_cfg, key)
    host = getattr(cfg, "HOST", "127.0.0.1")
    port = getattr(cfg, "PORT", 6379)
    db = getattr(cfg, "DB", 0)
    return f"redis://{host}:{port}/{db}"


def get_async_redis(key: Optional[str] = "DEFAULT") -> aioredis.Redis:
    """获取异步 Redis 客户端（与同步门面 redis_client() 取用方式对齐）

    - key=None 归一为 DEFAULT
    - 实例未在 settings.REDIS 登记时抛 KeyError（对齐同步门面语义）
    - 生产态：缓存复用（连接池共享）；测试态：每次新建（绑定当前事件循环）
    """
    if key is None:
        key = "DEFAULT"
    if not _IN_PYTEST:
        cached = _clients.get(key)
        if cached is not None:
            return cached

    redis_cfg = getattr(settings, "REDIS", {})
    if not hasattr(redis_cfg, "keys") or key not in redis_cfg.keys():
        raise KeyError(f"Async Redis '{key}' not found.")

    client = aioredis.from_url(
        _resolve_url(key), decode_responses=True, max_connections=100
    )
    if not _IN_PYTEST:
        _clients[key] = client
    return client


async def close_async_redis() -> None:
    """关闭并清空缓存的异步客户端（进程退出时调用）

    仅处理生产态缓存实例；测试态无缓存，本函数为空操作。
    """
    for client in _clients.values():
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001 退出路径兜底，不向上传播
            pass
    _clients.clear()
