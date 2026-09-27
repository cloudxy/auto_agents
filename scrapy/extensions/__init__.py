"""Scrapy Extensions - 爬虫生命周期钩子

包含两个扩展：
- SpiderCloseWebhook：爬虫关闭时向 Backend 回调任务终态（completed/failed），
  完成数据闭环的最后一步（任务 pending → running → completed/failed）
- IdleAutoClose：单次任务模式下空闲自动收尾（RedisSpider 常驻等待不会自然结束）

签名算法与 backend/app/external_api/v1/webhooks.py 保持一致：
    signature = HMAC-SHA256(secret, f"{timestamp}.{body}") 的 hex
配置见 config/default/webhook.yml（Backend 与 Scrapy 共享同一 Dynaconf 实例）。
"""
import hashlib
import hmac
import json
import time

import httpx
import redis
from scrapy import signals

from platform_core.logger import get_logger
from platform_core.queues import ACTIVE_TASK_KEY, ACTIVE_TASK_TTL, worker_active_key

logger = get_logger("spider")


class SpiderCloseWebhook:
    """爬虫关闭回调扩展

    仅当 Redis 中存在该爬虫的活跃任务关联（ACTIVE_TASK_KEY）时才回调，
    因此手动本地调试（无任务上下文）不会误触发。
    """

    def __init__(self, webhook_url: str, secret: str, redis_url: str):
        self.webhook_url = webhook_url
        self.secret = secret
        self.redis_url = redis_url
        self._local_tasks: dict[int, set[int]] = {}
        self._redis = None

    @classmethod
    def from_crawler(cls, crawler):
        from config import settings as project_settings

        ext = cls(
            webhook_url=project_settings.WEBHOOK.CALLBACK_URL,
            secret=str(project_settings.WEBHOOK.SECRET_KEY),
            redis_url=crawler.settings.get("REDIS_URL"),
        )
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(ext.request_scheduled, signal=signals.request_scheduled)
        return ext

    def _client(self):
        if self._redis is None:
            self._redis = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    def request_scheduled(self, request, spider):
        """本实例见过的 task_id：关闭时只回调这些，避免多 worker 互杀。"""
        tid = (request.meta or {}).get("task_id")
        if tid is None:
            return
        bucket = self._local_tasks.setdefault(id(spider), set())
        try:
            task_id = int(tid)
        except (TypeError, ValueError):
            return
        bucket.add(task_id)
        try:
            key = worker_active_key(spider.name)
            client = self._client()
            client.sadd(key, task_id)
            client.expire(key, ACTIVE_TASK_TTL)
        except Exception as e:  # noqa: BLE001 worker 键失败不阻断采集
            logger.debug(f"写入 worker 活跃键失败（忽略）: {spider.name}, error={e}")

    def spider_closed(self, spider, reason):
        local = self._local_tasks.pop(id(spider), set())
        members = {str(t) for t in local}
        if not members:
            try:
                client = self._client()
                members = client.smembers(worker_active_key(spider.name)) or set()
                if not members:
                    members = client.smembers(ACTIVE_TASK_KEY.format(spider_name=spider.name))
                    if len(members) > 1:
                        logger.info(
                            f"本实例未见 task_id 且全局多成员，跳过回调: {spider.name}"
                        )
                        return
            except Exception as e:  # noqa: BLE001 Redis 不可用：无法关联任务，跳过回调
                logger.warning(f"读取活跃任务集合失败，跳过回调: {spider.name}, error={e}")
                return
        if not members:
            logger.info(f"无活跃任务关联，跳过回调: {spider.name}")
            return

        task_ids = sorted(int(v) for v in members)
        status = "completed" if reason == "finished" else "failed"
        # item_scraped_count 由 StatsCollector 维护，是整个爬虫实例的共享统计：
        # 单任务时上报权威计数；并发多任务时无法区分归属，置 None 由 Backend 保留库内累加值
        item_count = (
            spider.crawler.stats.get_value("item_scraped_count", 0)
            if len(task_ids) == 1
            else None
        )
        for task_id in task_ids:
            self._callback_one(task_id, spider.name, status, item_count, reason)

    def _callback_one(self, task_id, spider_name, status, item_count, reason):
        """向 Backend 回调单个任务的终态（重试 3 次，最终失败由活跃键 TTL 兜底清理）"""
        body = json.dumps(
            {
                "task_id": task_id,
                "spider_name": spider_name,
                "status": status,
                "item_count": item_count,
                "error_message": None if status == "completed" else f"spider closed: {reason}",
            },
            ensure_ascii=False,
        )

        timestamp = str(int(time.time()))
        signature = hmac.new(
            self.secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256
        ).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Signature": signature,
        }

        # 回调可能遭遇瞬时失败（如 Backend 短暂繁忙），重试 3 次兜底，
        # 最终失败由 ACTIVE_TASK_TTL 过期机制清理关联（避免永久卡死）
        # trust_env=False：回调目标是本机 Backend，禁止走系统/环境代理，
        # 否则本机代理软件（如 Clash）会拦截 httpx 请求返回 502 空响应
        last_error = None
        for attempt in range(1, 4):
            try:
                resp = httpx.post(
                    self.webhook_url, content=body, headers=headers,
                    timeout=10, trust_env=False,
                )
                if resp.status_code == 200:
                    logger.info(f"任务终态已回调: task_id={task_id}, status={status}")
                    return
                last_error = f"http={resp.status_code}, body={resp.text}"
            except Exception as e:  # noqa: BLE001 网络异常：进入下一次重试
                last_error = str(e)
            logger.warning(f"任务终态回调未成功，准备重试: task_id={task_id}, 第 {attempt} 次, {last_error}")
            time.sleep(2)
        logger.error(f"任务终态回调失败（已重试 3 次）: task_id={task_id}, {last_error}")


class IdleAutoClose:
    """空闲自动收尾扩展（单次任务模式）

    RedisSpider 常驻等待新任务，不会自然走到 finished；当
    IDLE_CLOSE_SECONDS > 0 时，连续空闲超过阈值即以 finished 收尾
    （含 0 条，FR-19）→ 触发 SpiderCloseWebhook 回调任务终态。

    默认 30 秒；21600 是渠道探针锁，禁止当本窗。
    GWT-18.4 离线标注走 SPIDER_WORKER_OFFLINE_SECONDS（默认 120），不是本窗。
    常驻 Worker（scripts.runlib.spider 重生）：收尾回调后 run_forever 重生。
    """

    def __init__(self, idle_seconds: int):
        self.idle_seconds = idle_seconds
        self._idle_since = None
        self._has_items = False

    @classmethod
    def from_crawler(cls, crawler):
        ext = cls(crawler.settings.getint("IDLE_CLOSE_SECONDS", 0))
        if ext.idle_seconds > 0:
            crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
            crawler.signals.connect(ext.spider_closed_signal, signal=signals.spider_closed)
            crawler.signals.connect(ext.item_scraped, signal=signals.item_scraped)
            crawler.signals.connect(ext.spider_idle, signal=signals.spider_idle)
        return ext

    def spider_opened(self, spider):
        self._idle_since = None
        self._has_items = False

    def spider_closed_signal(self, spider, reason):
        # 收尾后重置，支持 CrawlerProcess 内多次 crawl
        self._idle_since = None
        self._has_items = False

    def item_scraped(self, item, response, spider):
        self._has_items = True
        self._idle_since = None  # 有产出即重置空闲计时

    def spider_idle(self, spider):
        now = time.monotonic()
        if self._idle_since is None:
            self._idle_since = now
            return
        if now - self._idle_since >= self.idle_seconds:
            logger.info(
                f"连续空闲 {self.idle_seconds}s，自动收尾: {spider.name} "
                f"items={int(self._has_items)}"
            )
            # 新版 scrapy 用协程版 close_spider_async(reason=...)，旧版回退 Deferred 版
            import asyncio

            engine = spider.crawler.engine
            close_async = getattr(engine, "close_spider_async", None)
            if close_async is not None:
                asyncio.ensure_future(close_async(reason="finished"))
            else:  # noqa: RET505 兼容旧版 scrapy
                engine.close_spider(spider, "finished")
