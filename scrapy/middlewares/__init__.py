"""Scrapy Middlewares - 高可用反爬与账号会话管理"""
import json
import random
import time
import hashlib

from scrapy import Item
from scrapy.exceptions import IgnoreRequest

from platform_core.logger import get_logger
from platform_core.queues import PROXY_SCORES_KEY, PROXY_STATS_KEY

logger = get_logger("spider")


def _get_site_config(spider) -> dict:
    """根据 spider.name 查找站点配置（sites.yml 中的站点段）

    配置路径：Scrapy settings.SITE_CONFIG → {sites: {<name>: {anti_crawl: {...}}}}
    或扁平化后直接 {<name>: {anti_crawl: {...}}}（取决于 Dynaconf 加载方式）。
    返回空 dict 表示无站点级覆盖，回退全局设置。
    """
    if spider is None:
        return {}
    settings_obj = getattr(spider, "settings", None)
    if settings_obj is None:
        return {}
    sites_cfg = settings_obj.get("SITE_CONFIG", {}) or {}
    # Dynaconf 把 sites.yml 的顶层键 "sites" 作为命名空间
    inner = sites_cfg.get("sites", sites_cfg) if isinstance(sites_cfg, dict) else {}
    site = inner.get(spider.name, {}) if isinstance(inner, dict) else {}
    return site if isinstance(site, dict) else {}


class TaskAttributionSpiderMiddleware:
    """任务归属中间件（阶段 4.1，注册在 SPIDER_MIDDLEWARES）

    把响应 meta 里的 task_id 注入到爬虫产出的每个 Item，
    StorePipeline 据此把结果精确关联回任务；
    并发多任务场景下不能再依赖活跃键反查（集合可能多成员）。
    """

    def process_spider_output(self, response, result, spider):
        task_id = response.meta.get("task_id")
        for element in result:
            if task_id is not None and isinstance(element, Item) and "task_id" not in element:
                element["task_id"] = task_id
            yield element


class AccountSessionMiddleware:
    """账号会话与指纹一致性中间件
    
    核心逻辑：
    1. 如果请求指定了 account_id，则从 Redis 获取该账号的固定 UA 和 Cookie。
    2. 禁止为已登录账号随机切换 UA，防止触发风控。
    3. 自动注入持久化的 Cookie。
    """
    def process_request(self, request, spider):
        account_id = request.meta.get('account_id')
        if not account_id:
            return None

        from utils.session_manager import SessionManager
        sm = SessionManager(account_id)
        session = sm.get_session()
        
        if not session.get('is_logged_in'):
            logger.warning(f"账号 [{account_id}] 会话失效，请重新登录")
            return None

        # 1. 强制使用账号绑定的 UA（指纹一致性）
        if session.get('ua'):
            request.headers['User-Agent'] = session['ua']
        
        # 2. 注入 Cookie
        if session.get('cookies'):
            request.cookies.update(session['cookies'])
            
        logger.debug(f"应用账号 [{account_id}] 的会话指纹")
        return None


class UserAgentMiddleware:
    """真实 UA 轮换中间件（仅针对未登录/无账号请求）

    站点配置联动（A3）：如果站点配置 anti_crawl.fixed_ua=true，
    使用 Scrapy 全局 USER_AGENT（固定指纹），不做随机轮换。
    """
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    ]

    def process_request(self, request, spider):
        # 如果已经由 AccountSessionMiddleware 处理过，则跳过
        if request.meta.get('account_id'):
            return None

        # 站点配置联动：fixed_ua=true 时使用固定 UA（不随机轮换）
        site_cfg = _get_site_config(spider)
        anti_crawl = site_cfg.get("anti_crawl", {}) if isinstance(site_cfg, dict) else {}
        if isinstance(anti_crawl, dict) and anti_crawl.get("fixed_ua") and spider is not None:
            fixed = getattr(spider, "settings", {}).get("USER_AGENT", "") if hasattr(getattr(spider, "settings", None), "get") else ""
            if fixed:
                request.headers["User-Agent"] = fixed
                return None

        ua = random.choice(self.USER_AGENTS)
        request.headers["User-Agent"] = ua
        return None


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


class RetryMiddleware:
    """智能重试中间件 - 动态调整延迟"""
    def process_response(self, request, response, spider):
        if response.status in [429, 500, 502, 503, 504]:
            logger.warning(f"触发风控/服务器错误 [{response.status}]，准备重试: {request.url}")
            retry_req = request.copy()
            retry_req.dont_filter = True
            # 遇到 429 自动增加延迟
            if response.status == 429:
                retry_req.meta["download_delay"] = 5
            return retry_req
        return response


class FingerprintMiddleware:
    """请求指纹中间件 - 辅助去重"""
    def process_request(self, request, spider):
        # 生成唯一指纹，用于日志追踪
        fp = hashlib.md5(request.url.encode()).hexdigest()[:8]
        request.meta["fingerprint"] = fp
        return None


class TaskControlMiddleware:
    """任务控制中间件 - 检查 Redis 控制键实现暂停/恢复/终止（A4）

    控制键：spider:task_control:{task_id}（string，value = pause/stop）
    - pause → 抛出 IgnoreRequest，跳过当前请求（爬虫继续运行，等待 resume）
    - stop  → close_spider 终止爬虫（reason="user_stopped"）
    - resume / 无键 → 正常放行

    使用 scrapy-redis 同一 Redis 连接（REDIS_URL），符合 B2 边界（scrapy 不 import backend）。
    """

    _CACHE_SECONDS = 2  # 控制键缓存周期（秒），避免每请求打 Redis

    def __init__(self, redis_url: str = ""):
        self._redis_url = redis_url
        self._client = None
        self._cached_at: float = 0.0

    @classmethod
    def from_crawler(cls, crawler):
        return cls(redis_url=crawler.settings.get("REDIS_URL", "") or "")

    def _get_client(self):
        if self._client is None and self._redis_url:
            try:
                import redis as redis_lib
                self._client = redis_lib.Redis.from_url(
                    self._redis_url, decode_responses=True
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"TaskControlMiddleware Redis 连接失败: {e}")
                return None
        return self._client

    def process_request(self, request, spider):
        task_id = request.meta.get("task_id")
        if not task_id:
            return None
        if not self._redis_url:
            return None

        client = self._get_client()
        if client is None:
            return None

        try:
            from platform_core.queues import TASK_CONTROL_KEY
            control_key = TASK_CONTROL_KEY.format(task_id=task_id)
            action = client.get(control_key)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"读取任务控制键失败: task_id={task_id}, error={e}")
            return None

        if not action:
            return None

        action = str(action).strip().lower()
        if action == "stop":
            logger.warning(f"用户终止任务，关闭爬虫: task_id={task_id}")
            spider.crawler.engine.close_spider(spider, reason="user_stopped")
            return None
        if action == "pause":
            logger.debug(f"任务已暂停，跳过请求: task_id={task_id}, url={request.url}")
            raise IgnoreRequest()
        # resume / 未知值 → 放行
        return None
