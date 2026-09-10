"""通用爬虫 - 配置化采集（免代码，对标 Spider-Flow）

任务条目经 start_urls 队列以 JSON 投递（消费者分发时包装）：
    {"url": "https://...", "task_id": 123, "selectors": [{"name": "title", "type": "xpath|css|regex", "expr": "..."}]}

解析时按选择器规则逐字段提取：
- xpath / css：走 Scrapy Selector，取全部匹配文本
- regex：对响应文本 re.findall
动态字段统一写入 Item 的 content（JSON 串），不引入运行期字段定义。
task_id 进请求 meta，由 TaskAttribution 中间件完成结果归属（并发安全）。

红线：反爬配置（下载延时 + UA）走 scrapy settings，任务参数不允许覆盖。
"""
from scrapy import Request
from scrapy.exceptions import DropItem
from scrapy_redis.spiders import RedisSpider

from platform_core.logger import get_logger
from spiders.base import parse_queue_entry
from utils.selector_engine import build_item, extract_fields

logger = get_logger("spider")


class GenericSpider(RedisSpider):
    """选择器规则随请求下发的通用采集爬虫"""

    name = "generic"
    redis_key = "generic:start_urls"
    # 采集目标由任务参数指定，不做域名白名单限制（风控由站点侧反爬配置兜底）

    def make_request_from_data(self, data):
        """start_urls 队列条目 → 请求（JSON 携带选择器 + task_id，纯 URL 兜底）"""
        url, task_id, extra = parse_queue_entry(data)
        selectors = extra.get("selectors") or []
        if not url:
            logger.warning(f"通用爬虫收到空 URL 条目，丢弃: {data!r}")
            return None
        meta = {"selectors": selectors}
        if task_id is not None:
            meta["task_id"] = int(task_id)
        return Request(url, meta=meta, dont_filter=True)

    def parse(self, response):
        """按 meta 中的选择器规则提取字段"""
        selectors = response.meta.get("selectors") or []
        logger.info(f"通用采集: {response.url} | selectors={len(selectors)}")

        fields = extract_fields(response, selectors)

        if not fields:
            raise DropItem(f"未提取到任何字段: {response.url}")

        yield build_item(response, fields, source="custom")
