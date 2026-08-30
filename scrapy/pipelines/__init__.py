"""Scrapy Pipelines - 数据清洗、验证与存储

数据出口（红线）：仅 Redis 队列，禁止直连 MySQL。
StorePipeline 把 Item 消息推送到 spider:item_queue，由 Backend 消费者落库。
"""
import json
import re
from datetime import datetime, timezone

import redis
from scrapy.exceptions import DropItem

from platform_core.logger import get_logger
from platform_core.queues import ACTIVE_TASK_KEY, ITEM_QUEUE

logger = get_logger("spider")


class CleanPipeline:
    """数据清洗管道 - 统一格式化与脱敏"""
    def process_item(self, item, spider):
        for field in item.fields:
            if field in item and isinstance(item[field], str):
                # 去除首尾空白和多余换行
                item[field] = re.sub(r'\s+', ' ', item[field].strip())
        return item


class ValidatePipeline:
    """数据验证管道 - 确保数据质量"""
    def process_item(self, item, spider):
        if not item.get('url'):
            raise DropItem(f"缺少必要字段 url: {item}")
        if not item.get('title'):
            logger.warning(f"数据缺失 title，但保留: {item.get('url')}")
        return item


class StorePipeline:
    """数据存储管道 - 把 Item JSON 推送到 Redis 结果队列（Backend 消费落库）

    消息格式（spider:item_queue）：
        {"task_id": int|None, "spider_name": str, "item_type": str,
         "item": {...}, "fetched_at": iso8601}
    task_id 优先取 Item 内部归属字段（TaskAttribution 中间件从响应 meta 注入，
    并发下精确）；缺失时回退活跃任务集合：唯一成员才归属，多成员置 None（防误关联）。
    """

    def open_spider(self, spider):
        # 复用 scrapy-redis 同一 REDIS_URL，保证连接目标一致
        self.redis = redis.Redis.from_url(
            spider.settings.get("REDIS_URL"), decode_responses=True
        )

    def close_spider(self, spider):
        try:
            self.redis.close()
        except Exception:  # noqa: BLE001 关闭路径兜底
            pass

    def process_item(self, item, spider):
        # 内部归属字段：弹出后再序列化，不进入业务字段存储；
        # 缺失时回退活跃任务集合（唯一成员才归属，多成员置 None 防误关联）
        task_id = item.pop("task_id", None)
        if task_id is None:
            try:
                members = self.redis.smembers(ACTIVE_TASK_KEY.format(spider_name=spider.name))
            except Exception as e:  # noqa: BLE001 Redis 抖动：本条结果不归属，不阻断采集
                logger.warning(f"读取活跃任务集合失败: {spider.name}, error={e}")
                members = set()
            if len(members) == 1:
                try:
                    task_id = int(next(iter(members)))
                except (TypeError, ValueError):
                    task_id = None
            elif len(members) > 1:
                logger.warning(
                    f"活跃任务集合多成员，结果不归属: {spider.name}, members={sorted(members)}"
                )

        message = json.dumps(
            {
                "task_id": task_id,
                "spider_name": spider.name,
                "item_type": type(item).__name__,
                "item": dict(item),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            default=str,
        )
        try:
            self.redis.rpush(ITEM_QUEUE, message)
            logger.debug(f"结果已推送队列: {ITEM_QUEUE}, task_id={task_id}")
        except Exception as e:  # noqa: BLE001 推送失败仅告警，不中断采集
            logger.error(f"结果推送队列失败: task_id={task_id}, error={e}")
        return item
