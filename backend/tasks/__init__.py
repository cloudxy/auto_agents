"""Backend 后台任务 - Redis 队列消费者

职责：
- 消费 spider:task_queue：任务 pending → running，并分发 start URL 给 scrapy-redis
- 消费 spider:item_queue：采集结果落库 spider_results，result_count 原子累加
- 任务终态（completed/failed）由 Webhook 回调推进，见 external_api/v1/webhooks.py
"""
from backend.tasks.consumer import SpiderTaskConsumer

__all__ = ["SpiderTaskConsumer"]
