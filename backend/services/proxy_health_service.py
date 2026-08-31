"""代理池健康管理 - 评分驱动的智能代理管理（B3）

职责：
- 后台定时探测低分代理，判断是否可恢复
- 提供代理评分排行查询（供 API 调用）
- 随 FastAPI lifespan 启动/停止

设计：
- 使用 redis.asyncio（Backend 侧异步 Redis，与 SpiderScheduler 一致）
- 探测 URL 使用 httpx HEAD 请求（轻量）
- 探测成功则恢复评分到 RECOVER_SCORE，失败则继续降低
"""
import asyncio
import json
from typing import Optional

import httpx
import redis.asyncio as aioredis

from config import settings
from platform_core.logger import get_logger
from platform_core.queues import PROXY_SCORES_KEY, PROXY_STATS_KEY
from platform_core.redis_async import get_async_redis

logger = get_logger("api")


def _build_probe_client(proxy: str, timeout: int) -> httpx.AsyncClient:
    """构造单代理探测 client（P0-4：httpx 0.28 已移除 proxies= 参数，改用 proxy=）

    proxy 逐代理绑定（无法在共享 client 上按请求切换），follow_redirects 对齐
    旧行为；trust_env=False 与 llm/notify/newapi 客户端同一约定（不走系统代理）。
    """
    return httpx.AsyncClient(
        proxy=proxy,
        timeout=timeout,
        follow_redirects=True,
        trust_env=False,
    )


class ProxyHealthService:
    """代理池健康管理 - 后台定时探测 + 评分查询"""

    def __init__(self):
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None
        self._redis: Optional[aioredis.Redis] = None

    async def start(self):
        """启动健康探测循环（随 FastAPI lifespan 调用）"""
        if not settings.get("PROXY_HEALTH.ENABLED", False):
            logger.info("代理健康管理已禁用（PROXY_HEALTH.ENABLED=false）")
            return
        self._redis = aioredis.from_url(
            settings.REDIS.DEFAULT.URL, decode_responses=True
        )
        self._running = True
        self._loop_task = asyncio.create_task(
            self._tick_loop(), name="proxy-health-checker"
        )
        interval = settings.get("PROXY_HEALTH.CHECK_INTERVAL", 300)
        logger.info(f"代理健康管理已启动: interval={interval}s")

    async def stop(self):
        """优雅停止"""
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
        logger.info("代理健康管理已停止")

    async def _tick_loop(self):
        """主循环：每 CHECK_INTERVAL 秒执行一轮探测"""
        interval = int(settings.get("PROXY_HEALTH.CHECK_INTERVAL", 300) or 300)
        while self._running:
            try:
                await self._health_check_once()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"代理健康探测异常: {e}")
            await asyncio.sleep(interval)

    async def _health_check_once(self):
        """单轮探测：
        1. 从 spider:proxy:scores 获取所有代理评分
        2. 对低分代理（< LOW_SCORE_THRESHOLD）发送探测请求
        3. 探测成功 → 恢复评分到 RECOVER_SCORE
        4. 探测失败 → 继续降低评分（扣 SCORE_DECAY）
        """
        if self._redis is None:
            return

        threshold = float(settings.get("PROXY_HEALTH.LOW_SCORE_THRESHOLD", 0.5) or 0.5)
        recover_score = float(settings.get("PROXY_HEALTH.RECOVER_SCORE", 0.5) or 0.5)
        probe_url = str(
            settings.get("PROXY_HEALTH.PROBE_URL", "https://httpbin.org/get")
            or "https://httpbin.org/get"
        )
        probe_timeout = int(settings.get("PROXY_HEALTH.PROBE_TIMEOUT", 10) or 10)
        score_decay = 0.1

        try:
            scores_raw = await self._redis.hgetall(PROXY_SCORES_KEY)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"读取代理评分失败: {e}")
            return

        if not scores_raw:
            return

        low_score_proxies = [
            proxy for proxy, score_str in scores_raw.items()
            if float(score_str) < threshold
        ]

        if not low_score_proxies:
            logger.debug("无低分代理，跳过本轮探测")
            return

        logger.info(f"开始探测 {len(low_score_proxies)} 个低分代理")

        for proxy in low_score_proxies:
            try:
                async with _build_probe_client(proxy, probe_timeout) as client:
                    resp = await client.head(probe_url)
                if resp.status_code < 500:
                    # 探测成功：恢复评分
                    await self._redis.hset(
                        PROXY_SCORES_KEY, proxy, str(recover_score)
                    )
                    # 更新 stats 的 last_check
                    await self._update_last_check(proxy)
                    logger.info(
                        f"代理探测成功，恢复评分: {proxy} → {recover_score}"
                    )
                else:
                    await self._decay_score(proxy, score_decay)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"代理探测失败: {proxy} | {e}")
                await self._decay_score(proxy, score_decay)

    async def _decay_score(self, proxy: str, decay: float) -> None:
        """降低代理评分（最低 0.0）"""
        if self._redis is None:
            return
        try:
            raw = await self._redis.hget(PROXY_SCORES_KEY, proxy)
            current = float(raw) if raw else 0.0
            new_score = max(0.0, current - decay)
            await self._redis.hset(PROXY_SCORES_KEY, proxy, str(round(new_score, 4)))
            await self._update_last_check(proxy)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"降低代理评分失败: proxy={proxy}, error={e}")

    async def _update_last_check(self, proxy: str) -> None:
        """更新 stats 中的 last_check 时间戳"""
        if self._redis is None:
            return
        import time
        try:
            raw = await self._redis.hget(PROXY_STATS_KEY, proxy)
            stats = json.loads(raw) if raw else {
                "success": 0, "fail": 0, "avg_latency": 0.0, "last_check": ""
            }
            stats["last_check"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            await self._redis.hset(PROXY_STATS_KEY, proxy, json.dumps(stats))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"更新 last_check 失败: proxy={proxy}, error={e}")

    async def get_proxy_health(self) -> list[dict]:
        """返回代理评分排行（供 API 调用）

        返回格式：
        [
            {
                "proxy": "http://...",
                "score": 0.85,
                "success": 120,
                "fail": 5,
                "avg_latency": 1.23,
                "last_check": "2024-01-01T12:00:00"
            },
            ...
        ]
        """
        # 读接口统一走异步门面（P2-16/17 修复：不再每请求新建连接再关闭；
        # 门面实例由门面管理生命周期，调用方禁止 close）
        redis = get_async_redis()
        scores_raw = await redis.hgetall(PROXY_SCORES_KEY)
        stats_raw = await redis.hgetall(PROXY_STATS_KEY)

        result = []
        all_proxies = set(scores_raw.keys()) | set(stats_raw.keys())
        for proxy in all_proxies:
            score = float(scores_raw.get(proxy, 0.0))
            stats = {}
            raw = stats_raw.get(proxy)
            if raw:
                try:
                    stats = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    stats = {}
            result.append({
                "proxy": proxy,
                "score": round(score, 4),
                "success": stats.get("success", 0),
                "fail": stats.get("fail", 0),
                "avg_latency": round(stats.get("avg_latency", 0.0) or 0.0, 3),
                "last_check": stats.get("last_check", ""),
            })

        # 按评分降序排列
        result.sort(key=lambda x: x["score"], reverse=True)
        return result
