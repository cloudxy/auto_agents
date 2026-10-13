"""代理池轮换中间件（经 middlewares 包重导出：settings 按 middlewares.ProxyMiddleware 点路径加载）"""
import json
import random
import time

from platform_core.logger import get_logger
from platform_core.queues import PROXY_SCORES_KEY, PROXY_STATS_KEY

from .site_config import _get_site_config

logger = get_logger("spider")


class ProxyMiddleware:
    """代理池轮换中间件 - 评分驱动的智能代理管理（B3）

    代理源（优先级从高到低）：
    1. Redis 动态池（配置 PROXY_REDIS_KEY，List 结构，带缓存刷新）
    2. 静态列表（配置 PROXY_LIST，如 ["http://user:pass@host:port"]）

    评分机制：
    - score = success_rate × 0.6 + (1 - min(avg_latency / 10.0, 1.0)) × 0.4
    - 按评分加权随机选择（无评分新代理默认 0.5）
    - 评分低于 LOW_SCORE_THRESHOLD（默认 0.2）时加入 failed_proxies 剔除

    未启用（PROXY_ENABLED=false）或池为空时直连。
    """

    _REFRESH_SECONDS = 60  # Redis 池缓存刷新周期，避免每请求打 Redis
    _DEFAULT_SCORE = 0.5   # 新代理默认评分
    _SCORE_DECAY = 0.1     # 每次失败扣减的评分

    def __init__(
        self,
        enabled=False,
        proxy_list=None,
        redis_key="",
        redis_url="",
        low_score_threshold=0.2,
    ):
        self.enabled = enabled
        self._static_proxies = list(proxy_list or [])
        self._redis_key = redis_key
        self._redis_url = redis_url
        self._low_score_threshold = low_score_threshold
        self.failed_proxies: set[str] = set()
        self._cached_pool: list[str] = []
        self._cached_at: float = 0.0
        self._redis_client = None  # 延迟初始化，复用同一连接

    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        return cls(
            enabled=settings.getbool("PROXY_ENABLED", False),
            proxy_list=settings.getlist("PROXY_LIST") or [],
            redis_key=settings.get("PROXY_REDIS_KEY", "") or "",
            redis_url=settings.get("REDIS_URL", "") or "",
            low_score_threshold=float(
                settings.get("PROXY_HEALTH.LOW_SCORE_THRESHOLD", 0.2) or 0.2
            ),
        )

    def _get_redis(self):
        """延迟初始化同步 Redis 客户端（复用连接）"""
        if self._redis_client is None and self._redis_url:
            try:
                import redis as redis_lib
                self._redis_client = redis_lib.Redis.from_url(
                    self._redis_url, decode_responses=True
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"ProxyMiddleware Redis 连接失败: {e}")
                return None
        return self._redis_client

    def _load_pool(self) -> list[str]:
        """当前可用代理池：Redis 动态池（带缓存）优先，其次静态列表"""
        if self._redis_key and self._redis_url:
            now = time.monotonic()
            if now - self._cached_at >= self._REFRESH_SECONDS:
                try:
                    import redis as redis_lib

                    client = redis_lib.Redis.from_url(
                        self._redis_url, decode_responses=True
                    )
                    pool = [p for p in client.lrange(self._redis_key, 0, -1) if p]
                    client.close()
                    self._cached_pool = pool
                    self._cached_at = now
                    logger.debug(f"代理池已从 Redis 刷新: key={self._redis_key}, count={len(pool)}")
                except Exception as e:  # noqa: BLE001 Redis 不可用时回退静态列表/直连
                    logger.warning(f"拉取 Redis 代理池失败，回退: {e}")
                    self._cached_at = now
            if self._cached_pool:
                return self._cached_pool
        return self._static_proxies

    @property
    def proxies(self) -> list[str]:
        return self._load_pool()

    def _load_scores(self) -> dict[str, float]:
        """从 Redis 加载代理评分（HASH spider:proxy:scores）"""
        client = self._get_redis()
        if client is None:
            return {}
        try:
            raw = client.hgetall(PROXY_SCORES_KEY)
            return {proxy: float(score) for proxy, score in raw.items()}
        except Exception as e:  # noqa: BLE001
            logger.warning(f"加载代理评分失败: {e}")
            return {}

    def _weighted_choice(self, available: list[str]) -> str:
        """按评分加权随机选择代理；无评分的新代理给默认分 0.5"""
        scores = self._load_scores()
        weights = [scores.get(proxy, self._DEFAULT_SCORE) for proxy in available]
        return random.choices(available, weights=weights, k=1)[0]

    def _update_stats(
        self, proxy: str, success: bool, latency: float | None = None
    ) -> None:
        """更新代理统计（success/fail 计数 + avg_latency）并重算评分"""
        client = self._get_redis()
        if client is None:
            return
        try:
            raw = client.hget(PROXY_STATS_KEY, proxy)
            stats = json.loads(raw) if raw else {
                "success": 0, "fail": 0, "avg_latency": 0.0, "last_check": ""
            }
            if success:
                stats["success"] = stats.get("success", 0) + 1
                if latency is not None:
                    old_avg = stats.get("avg_latency", 0.0) or 0.0
                    n = stats["success"]
                    stats["avg_latency"] = (old_avg * (n - 1) + latency) / n
            else:
                stats["fail"] = stats.get("fail", 0) + 1
            stats["last_check"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            client.hset(PROXY_STATS_KEY, proxy, json.dumps(stats))

            # 重算评分：
            # - 无成功记录时直接置 0.0（避免 latency 项托底导致失败代理无法剔除）
            # - 有成功时：score = success_rate × 0.6 + (1 - min(avg_latency/10, 1)) × 0.4
            total = stats["success"] + stats["fail"]
            if stats["success"] == 0 or total == 0:
                score = 0.0
            else:
                success_rate = stats["success"] / total
                lat_penalty = min((stats.get("avg_latency", 0.0) or 0.0) / 10.0, 1.0)
                score = success_rate * 0.6 + (1.0 - lat_penalty) * 0.4
            client.hset(PROXY_SCORES_KEY, proxy, str(round(score, 4)))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"更新代理统计失败: proxy={proxy}, error={e}")

    def process_request(self, request, spider):
        # 站点配置联动（A3）：proxy_enabled=false 时即使全局 PROXY_ENABLED=true 也直连
        site_cfg = _get_site_config(spider)
        anti_crawl = site_cfg.get("anti_crawl", {}) if isinstance(site_cfg, dict) else {}
        if isinstance(anti_crawl, dict) and anti_crawl.get("proxy_enabled") is False:
            return None
        if not self.enabled:
            return None
        available = [p for p in self.proxies if p not in self.failed_proxies]
        if not available:
            logger.warning("代理池为空或全部失效，直连")
            return None

        # 评分加权随机选择（替代均匀 random.choice）
        proxy = self._weighted_choice(available)
        request.meta["proxy"] = proxy
        request.meta["_proxy_start_time"] = time.monotonic()
        return None

    def process_response(self, request, response, spider):
        """请求成功：记录 success + download_latency，更新评分"""
        proxy = request.meta.get("proxy")
        if not proxy or not self.enabled:
            return response
        latency = None
        start_time = request.meta.get("_proxy_start_time")
        if start_time is not None:
            latency = time.monotonic() - start_time
        # 也尝试从 Scrapy 自带的 download_latency 读取
        dl_latency = request.meta.get("download_latency")
        if dl_latency is not None:
            latency = dl_latency
        self._update_stats(proxy, success=True, latency=latency)
        return response

    def process_exception(self, request, exception, spider):
        """请求失败：降低评分；仅当评分低于阈值时才加入 failed_proxies 剔除"""
        proxy = request.meta.get("proxy")
        if not proxy or not self.enabled:
            return None
        self._update_stats(proxy, success=False)
        # 读取最新评分，决定是否剔除
        client = self._get_redis()
        score = self._DEFAULT_SCORE
        if client is not None:
            try:
                raw_score = client.hget(PROXY_SCORES_KEY, proxy)
                if raw_score is not None:
                    score = float(raw_score)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"读取代理评分失败: proxy={proxy}, error={e}")
        if score < self._low_score_threshold:
            self.failed_proxies.add(proxy)
            logger.warning(
                f"代理评分低于阈值({self._low_score_threshold})，剔除: "
                f"{proxy} | score={score:.3f} | Error: {exception}"
            )
        else:
            logger.debug(
                f"代理请求失败但评分尚可，保留: {proxy} | score={score:.3f} | Error: {exception}"
            )
        return None
