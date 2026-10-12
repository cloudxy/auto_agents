"""Scrapy Middlewares - 高可用反爬与账号会话管理"""
import random
import time
import hashlib

from scrapy import Item
from scrapy.exceptions import IgnoreRequest

from platform_core.logger import get_logger

# 重导出：settings / config 按 middlewares.ProxyMiddleware 点路径加载，爬虫经 middlewares 取站点配置
from .proxy import ProxyMiddleware  # noqa: F401
from .site_config import _get_site_config

logger = get_logger("spider")


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


class RetryMiddleware:
    """智能重试中间件 - 风控/5xx 按上限重试（P0-1 修复）

    旧缺陷（2026-08-31 审计 P0-1）：无条件重试且无次数上限、download_delay
    是 Scrapy 不读的自创 meta 键 → 429 风暴下爬虫永不空闲、任务永久卡 running。

    现语义：
    - 与内置 RetryMiddleware 同名 meta 约定（retry_times）计数，达到
      RETRY_TIMES 上限后放行响应交由上层处理（终态可被 webhook/超时回收闭环）
    - 429 时把下载槽位延迟指数上调（对齐内置中间件的动态延迟调整思路），
      不再使用无效的自创 meta 键；取不到槽位则跳过（重试上限仍兜底）
    """
    RETRY_STATUSES = (429, 500, 502, 503, 504)
    _SLOT_DELAY_CAP = 60.0  # 槽位延迟上调上限（秒）

    def __init__(self, max_retries: int = 3, backoff_base: float = 5.0):
        self._max_retries = max(1, int(max_retries))
        self._backoff_base = float(backoff_base)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            max_retries=crawler.settings.getint("RETRY_TIMES", 3),
            backoff_base=crawler.settings.getfloat("RETRY_BACKOFF_BASE", 5.0),
        )

    def process_response(self, request, response, spider):
        if response.status not in self.RETRY_STATUSES:
            return response
        if request.meta.get("dont_retry"):
            return response
        retry_times = int(request.meta.get("retry_times", 0))
        if retry_times >= self._max_retries:
            logger.warning(
                f"响应 [{response.status}] 重试 {retry_times} 次已达上限，放行: {request.url}"
            )
            return response
        if response.status == 429:
            self._bump_download_delay(request, spider, retry_times)
        retry_req = request.copy()
        retry_req.dont_filter = True
        retry_req.meta["retry_times"] = retry_times + 1
        logger.warning(
            f"触发风控/服务器错误 [{response.status}]，"
            f"第 {retry_times + 1}/{self._max_retries} 次重试: {request.url}"
        )
        return retry_req

    def _bump_download_delay(self, request, spider, retry_times: int) -> None:
        """429 时临时抬高下载槽位延迟（尽力而为，取不到槽位则跳过）"""
        delay = self._backoff_base * (2 ** retry_times)
        crawler = getattr(spider, "crawler", None)
        engine = getattr(crawler, "engine", None)
        downloader = getattr(engine, "downloader", None)
        if downloader is None:
            return
        slot_key = request.meta.get("download_slot")
        slot = downloader.slots.get(slot_key) if slot_key else None
        if slot is None:
            return
        slot.delay = min(max(slot.delay, delay), self._SLOT_DELAY_CAP)
        logger.warning(
            f"429 风控：下载槽位延迟上调至 {slot.delay:.0f}s: slot={slot_key}"
        )


class OutboundGuardMiddleware:
    """出站守卫（审计 BUG-22 / F4-1 / P0-8）：禁止爬虫请求内网 / 回环 / 链路本地 / 云元数据地址

    - 目标来自租户（AI 计划、通用 / 流程爬虫的 urls），必须在真正下载前拦截；
    - 只放行 http(s)（file:// ftp:// s3:// 等一律拒绝，防本地文件读取）；
    - 重定向产生的新请求会重新经过下载中间件，因此每一跳都复检；
    - 解析结果按主机缓存 5 分钟，避免每个请求阻塞 reactor 做 DNS。
    已知边界：Playwright 渲染时浏览器自行加载的子资源不经过本中间件（P1-6 统一收口）。
    """

    _CACHE_SECONDS = 300.0

    def __init__(self, enabled: bool = True, allowed_hosts=()):
        self._enabled = enabled
        self._allowed_hosts = tuple(allowed_hosts or ())
        self._cache: dict = {}

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            enabled=crawler.settings.getbool("OUTBOUND_GUARD_ENABLED", True),
            allowed_hosts=crawler.settings.getlist("OUTBOUND_GUARD_ALLOWED_HOSTS"),
        )

    def _verdict(self, url: str) -> str:
        """返回拒绝原因；放行返回空串"""
        from urllib.parse import urlparse

        from platform_core.outbound_guard import OutboundBlocked, check_url, host_allowed

        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme in ("http", "https") and host and self._allowed_hosts \
                and host_allowed(host, self._allowed_hosts):
            return ""
        key = (parsed.scheme, host)
        now = time.time()
        cached = self._cache.get(key)
        if cached is not None and now - cached[1] < self._CACHE_SECONDS:
            return cached[0]
        try:
            check_url(url, allowed_ports=None)
            reason = ""
        except OutboundBlocked as exc:
            reason = exc.message
        self._cache[key] = (reason, now)
        return reason

    def process_request(self, request, spider):
        if not self._enabled or request.url.startswith(("data:", "about:")):
            return None
        reason = self._verdict(request.url)
        if not reason:
            # 决策 D8：站点级豁免 robots.txt（本中间件优先级 50，先于 robots 中间件 100 执行）
            from urllib.parse import urlparse

            from platform_core.outbound_guard import robots_exempt

            if robots_exempt((urlparse(request.url).hostname or "").lower()):
                request.meta["dont_obey_robotstxt"] = True
        if reason:
            logger.warning(
                f"出站守卫拒绝请求: spider={getattr(spider, 'name', '?')} "
                f"task_id={request.meta.get('task_id')} url={request.url[:200]} reason={reason}"
            )
            raise IgnoreRequest(f"出站守卫拒绝: {reason}")
        return None


from scrapy.downloadermiddlewares.robotstxt import RobotsTxtMiddleware  # noqa: E402


class PoliteRobotsTxtMiddleware(RobotsTxtMiddleware):
    """robots.txt 拒绝时记一条带 task_id 的告警（决策 D8）

    Scrapy 原生只打 DEBUG，租户看到的是「0 条结果」却不知道原因；这里把原因写进任务日志。
    只有 ROBOTSTXT_OBEY=true 的爬虫（租户填地址的通用 / 流程爬虫）启用，其余抛 NotConfigured。
    """

    def process_request_2(self, rp, request):
        try:
            super().process_request_2(rp, request)
        except IgnoreRequest:
            logger.warning(
                f"目标站点 robots.txt 不允许采集: task_id={request.meta.get('task_id')} "
                f"url={request.url[:200]}（平台默认遵守 robots.txt）"
            )
            raise


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
            # 审计 BUG-15：只丢弃该任务的请求。原先 close_spider 关闭整个共享实例，
            # 同实例上其他租户的任务一起被杀；任务终态由后端直接置 cancelled
            logger.info(f"任务已终止，丢弃其请求: task_id={task_id}, url={request.url}")
            raise IgnoreRequest()
        if action == "pause":
            logger.debug(f"任务已暂停，跳过请求: task_id={task_id}, url={request.url}")
            raise IgnoreRequest()
        # resume / 未知值 → 放行
        return None
