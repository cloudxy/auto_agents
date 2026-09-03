"""LLM token 用量服务 - Redis 实时计数 + 定时聚合落库（P0-3 用量持久化）

背景（审计 P0-3）：llm_client 的 _TOKEN_USAGE 是纯进程内存——重启清零、
多副本无法聚合、无落库，预算熔断形同虚设。本模块补齐计量底座：

- record_usage：每次 LLM 调用成功后 INCRBY Redis（日粒度明细 + 月粒度汇总）
- get_month_used：预算熔断读数（月度累计；None = Redis 不可用，调用方回退内存）
- LlmUsageFlushService：随 lifespan 启动的后台任务，周期把 Redis 日粒度计数
  聚合 upsert 到 llm_token_usage 表（分布式锁防多实例重复聚合）

Redis 键约定（与 platform_core.queues 的键名契约风格一致）：
- llm:usage:d:{yyyymmdd}   hash：field = "{dim}|{model}|{metric}"，待聚合日明细
- llm:usage:m:{yyyymm}     hash：field = "{dim}|total"，预算读数（TTL 93 天）
- llm:usage:d:{...}#claim  聚合过程中的冻结键（rename 原子认领，防并发增量丢失）

dim 即 llm_client 的 usage_dim："provider:<id>" 或 "config"。
"""
import asyncio
import sys
import time
from datetime import date
from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from backend.config_consts import (LLM_USAGE_FLUSH_INTERVAL)
from platform_core.db import get_manager
from platform_core.logger import get_logger
from platform_core.queues import distributed_lock
from platform_core.redis_async import get_async_redis
from backend.repositories.llm_token_usage_repository import LlmTokenUsageRepository

logger = get_logger("api")

# 测试态不触网（与 platform_core/redis_async.py 同一约定）：用量读写回退
# 调用方内存语义（llm_client._TOKEN_USAGE），存量预算测试行为零变化
_IN_PYTEST = "pytest" in sys.modules

_DAILY_KEY_PREFIX = "llm:usage:d:"
_MONTHLY_KEY_PREFIX = "llm:usage:m:"
_CLAIM_SUFFIX = "#claim"
_FLUSH_LOCK_KEY = "llm:usage:flush:lock"
# 月度键 TTL：覆盖当月 + 跨月查询余量（93 天）
_MONTHLY_TTL = 93 * 86400
# B3：日明细 30 天 TTL（聚合 flush 后即可过期，防永生 hash）
_DAILY_TTL = 30 * 86400
# hash field 指标名（写入与聚合解析共用）
_METRICS = ("prompt", "completion", "total", "requests", "failed")


def _today() -> date:
    return date.fromtimestamp(time.time())


def _daily_key(day: date) -> str:
    return f"{_DAILY_KEY_PREFIX}{day.strftime('%Y%m%d')}"


def _monthly_key(day: date) -> str:
    return f"{_MONTHLY_KEY_PREFIX}{day.strftime('%Y%m')}"


def _parse_provider_id(dim: str) -> Optional[int]:
    """dim → provider_id：provider:9 → 9；config → None"""
    if dim.startswith("provider:"):
        try:
            return int(dim.split(":", 1)[1])
        except ValueError:
            return None
    return None


# 记录一次 LLM 调用用量（实时 INCRBY；任何失败仅记日志，不影响主调用路径）。
# dim 即 llm_client 的用量维度："provider:<id>" 或 "config"。
async def record_usage(dim: str, model: str, prompt_tokens: int = 0, completion_tokens: int = 0, total_tokens: int = 0, failed: bool = False, tenant_id: Optional[int] = None) -> None:
    logger.debug(f"记录 LLM 用量: dim={dim}, model={model}, total={total_tokens}, failed={failed}, tenant={tenant_id}")
    # S1 接线：Redis field 四段（tenant|dim|model|metric），旧三段数据 flush 时归默认租户
    tkey = str(tenant_id) if tenant_id is not None else "default"
    if _IN_PYTEST:
        return
    total = int(total_tokens or 0)
    prompt = int(prompt_tokens or 0)
    completion = int(completion_tokens or 0)
    if total <= 0 and prompt <= 0 and completion <= 0 and not failed:
        return
    today = _today()
    try:
        redis = get_async_redis()
        daily = _daily_key(today)
        # LLM 调用频率低（AI 规划场景），直连 INCRBY 足够；非 pipeline 便于桩测
        if prompt:
            await redis.hincrby(daily, f"{tkey}|{dim}|{model}|prompt", prompt)
        if completion:
            await redis.hincrby(daily, f"{tkey}|{dim}|{model}|completion", completion)
        if total:
            await redis.hincrby(daily, f"{tkey}|{dim}|{model}|total", total)
            await redis.hincrby(daily, f"{tkey}|{dim}|{model}|requests", 1)
            # 月度汇总（预算读数口径）
            monthly = _monthly_key(today)
            await redis.hincrby(monthly, f"{dim}|total", total)
            await redis.expire(monthly, _MONTHLY_TTL)
        if failed:
            await redis.hincrby(daily, f"{tkey}|{dim}|{model}|failed", 1)
        await redis.expire(daily, _DAILY_TTL)
    except Exception as e:  # noqa: BLE001 用量记录失败不影响 LLM 主路径
        logger.debug(f"LLM 用量 Redis 记录失败（忽略，预算回退内存读数）: dim={dim}, error={e}")


# 读取当月累计 token 用量（预算熔断读数）；返回 None 表示 Redis 不可用/测试态，
# 调用方（llm_client）应回退进程内存计数。
async def get_month_used(dim: str, tenant_id: Optional[int] = None) -> Optional[int]:
    logger.debug(f"读取月度 LLM 用量: dim={dim}")
    if _IN_PYTEST:
        return None
    try:
        redis = get_async_redis()
        tkey = str(tenant_id) if tenant_id is not None else "default"
        raw = await redis.hget(_monthly_key(_today()), f"{tkey}|{dim}|total")
        if not raw and tkey != "default":
            raw = await redis.hget(_monthly_key(_today()), f"{dim}|total")  # 旧三段兜底
        return int(raw) if raw else 0
    except Exception as e:  # noqa: BLE001
        logger.debug(f"LLM 月度用量读取失败（回退内存读数）: dim={dim}, error={e}")
        return None


class LlmUsageFlushService:
    """Redis 日粒度用量 → llm_token_usage 表的定时聚合任务（随 lifespan 启停）"""

    def __init__(self):
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None
        self._redis: Optional[aioredis.Redis] = None

    async def start(self) -> None:
        if not settings.get("LLM.USAGE_PERSIST_ENABLED", True):
            logger.info("LLM 用量落库已禁用（LLM.USAGE_PERSIST_ENABLED=false）")
            return
        # B3：归一异步 Redis 门面（共享连接池，键契约见 platform_core.queues）
        from platform_core.redis_async import get_async_redis

        self._redis = get_async_redis()
        self._running = True
        self._loop_task = asyncio.create_task(self._flush_loop(), name="llm-usage-flush")
        interval = int(settings.get("LLM.USAGE_FLUSH_INTERVAL", LLM_USAGE_FLUSH_INTERVAL) or 60)
        logger.info(f"LLM 用量聚合任务已启动: interval={interval}s")

    async def stop(self) -> None:
        self._running = False
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        logger.info("LLM 用量聚合任务已停止")

    async def _flush_loop(self) -> None:
        interval = int(settings.get("LLM.USAGE_FLUSH_INTERVAL", LLM_USAGE_FLUSH_INTERVAL) or 60)
        while self._running:
            try:
                await self.flush_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 单轮失败不中断循环
                logger.warning(f"LLM 用量聚合异常: {e}")
            await asyncio.sleep(max(1, interval))

    async def flush_once(self) -> int:
        """扫描待聚合日键并落库，返回本轮聚合的行数

        并发防护（两层）：
        1. 分布式锁：多实例部署时同一轮只有一个实例聚合；
        2. rename 认领：把日键原子改名为 #claim 后再读值——认领后新增量会写入
           新建的日键（不丢），本轮值冻结；落库成功后删除认领键。
           崩溃残留的 #claim 键下一轮仍被扫描（匹配同一前缀），at-least-once。
        """
        if self._redis is None:
            return 0
        keys = [k async for k in self._redis.scan_iter(match=f"{_DAILY_KEY_PREFIX}*")]
        if not keys:
            return 0
        lock_ttl = max(60, int(settings.get("LLM.USAGE_FLUSH_INTERVAL", LLM_USAGE_FLUSH_INTERVAL) or 60) * 2)
        async with distributed_lock(self._redis, _FLUSH_LOCK_KEY, ttl=lock_ttl) as lock:
            if lock is None:
                return 0  # 其他实例聚合中
            total_rows = 0
            for key in keys:
                try:
                    total_rows += await self._flush_one(key)
                except Exception as e:  # noqa: BLE001 单键失败不影响其余键
                    logger.warning(f"LLM 用量聚合单键失败（下轮重试）: key={key}, error={e}")
            return total_rows

    async def _flush_one(self, key: str) -> int:
        """聚合单个日键：rename 认领 → 解析 → upsert → 删除认领键"""
        claimed = f"{key}{_CLAIM_SUFFIX}"
        try:
            await self._redis.rename(key, claimed)
        except Exception as e:  # noqa: BLE001 键不存在（他轮已处理）等场景直接跳过
            logger.debug(f"LLM 用量日键认领失败（跳过）: key={key}, error={e}")
            return 0
        fields = await self._redis.hgetall(claimed)
        if not fields:
            await self._redis.delete(claimed)
            return 0

        day_str = claimed[len(_DAILY_KEY_PREFIX):].split("#", 1)[0]
        try:
            stat_date = date(int(day_str[:4]), int(day_str[4:6]), int(day_str[6:8]))
        except ValueError:
            logger.warning(f"LLM 用量日键日期段非法（丢弃该键）: key={claimed}")
            await self._redis.delete(claimed)
            return 0

        rows = self._build_rows(fields, stat_date)
        row_count = 0
        if rows:
            from backend.services.background_session import default_tenant_id

            async with AsyncSession(self._engine()) as session:
                # tenant_key（数字串/default）→ tenant_id；default 按需查建
                default_tid = None
                for row in rows:
                    if row.get("tenant_key") in (None, "default", "legacy"):
                        default_tid = default_tid or await default_tenant_id(session)
                        row["tenant_id"] = default_tid
                    else:
                        try:
                            row["tenant_id"] = int(row["tenant_key"])
                        except (TypeError, ValueError):
                            row["tenant_id"] = default_tid or await default_tenant_id(session)
                await LlmTokenUsageRepository(session).upsert_daily(rows)
                await session.commit()
            row_count = len(rows)
        await self._redis.delete(claimed)
        if row_count:
            logger.info(f"LLM 用量聚合落库: date={stat_date}, rows={row_count}")
        return row_count

    @staticmethod
    def _build_rows(fields: dict, stat_date: date) -> list[dict]:
        """把 hash fields 解析为 upsert 行（坏字段值按 0 容错跳过）"""
        grouped: dict[tuple[str, str, str], dict] = {}
        for field, value in fields.items():
            parts = field.split("|")
            if len(parts) == 4:
                _tkey, dim, model, metric = parts
            elif len(parts) == 3:
                _tkey, dim, model, metric = "legacy", *parts  # 旧三段标记 legacy（flush 侧归默认租户）
            else:
                continue
            if metric not in _METRICS:
                continue
            row = grouped.setdefault(
                (_tkey, dim, model),
                {
                    "tenant_key": _tkey,
                    "provider_id": _parse_provider_id(dim),
                    "provider_name": dim,
                    "model": model,
                    "stat_date": stat_date,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "request_count": 0,
                    "failed_count": 0,
                },
            )
            try:
                amount = int(value)
            except (TypeError, ValueError):
                continue
            if metric == "prompt":
                row["prompt_tokens"] += amount
            elif metric == "completion":
                row["completion_tokens"] += amount
            elif metric == "total":
                row["total_tokens"] += amount
            elif metric == "requests":
                row["request_count"] += amount
            elif metric == "failed":
                row["failed_count"] += amount
        return list(grouped.values())

    @staticmethod
    def _engine():
        return get_manager().async_engines["DEFAULT"]
