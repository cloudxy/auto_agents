"""任务感知爬虫基类（阶段 4.1）

Backend 消费者投递的 start_urls 队列条目统一为 JSON：
    {"url": "https://...", "task_id": 123, ...}
基类负责解析条目并把 task_id 注入请求 meta，供 TaskAttributionSpiderMiddleware
把结果归属到任务（并发下不能再依赖活跃键反查）。纯 URL 条目保持兼容。
"""
import json

from scrapy import Request
from scrapy_redis.spiders import RedisSpider

from platform_core.logger import get_logger

logger = get_logger("spider")


def parse_queue_entry(data):
    """解析 start_urls 队列条目 → (url, task_id, extra)

    - JSON 条目：{"url": ..., "task_id": ...}，其余键放 extra（如 selectors）
    - 纯 URL 字符串：task_id=None（兜底路径，结果归属走活跃集合唯一成员）
    """
    logger.debug("解析 start_urls 队列条目")
    try:
        entry = json.loads(data)
    except (TypeError, ValueError):
        return data, None, {}
    if isinstance(entry, dict) and entry.get("url"):
        task_id = entry.get("task_id")
        extra = {k: v for k, v in entry.items() if k not in ("url", "task_id")}
        return entry["url"], task_id, extra
    return data, None, {}


class TaskAwareRedisSpider(RedisSpider):
    """解析 JSON 队列条目并把 task_id 注入请求 meta 的 RedisSpider

    P1-7 接线（2026-08-31）：sites.yml 的站点级 anti_crawl.download_delay
    在此消费——按爬虫名匹配站点段，命中则覆盖 spider.download_delay
    （下载槽位创建时读取该属性，等效站点级延迟）；login_required 站点
    打印告警（账号会话体系尚未实现，见审计报告 P1-7 备注）。
    """

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        try:
            from middlewares import _get_site_config

            site_cfg = _get_site_config(spider)
        except Exception as e:  # noqa: BLE001 配置异常不阻断爬虫启动
            logger.warning(f"读取站点配置失败（回退全局反爬设置）: {spider.name}, error={e}")
            return spider
        anti_crawl = site_cfg.get("anti_crawl") or {}
        delay = anti_crawl.get("download_delay") if hasattr(anti_crawl, "get") else None
        if delay:
            spider.download_delay = float(delay)
            logger.info(f"站点级下载延迟生效: {spider.name} → {delay}s")
        if site_cfg.get("login_required"):
            logger.warning(
                f"站点标记需登录态，但账号会话体系未实现，采集可能受限: {spider.name}"
            )
        return spider

    def make_request_from_data(self, data):
        url, task_id, _extra = parse_queue_entry(data)
        if not url:
            logger.warning(f"收到空 URL 条目，丢弃: {data!r}")
            return None
        meta = {}
        if task_id is not None:
            meta["task_id"] = int(task_id)
        return Request(url, meta=meta, dont_filter=True)
