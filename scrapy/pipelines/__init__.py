"""Scrapy Pipelines - 数据清洗、验证与存储"""
import re
from scrapy.exceptions import DropItem
from core.log_init import get_logger

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
    """数据存储管道 - 发送到 Backend API 或持久化"""
    def process_item(self, item, spider):
        # TODO: 实现将 Item 转换为 JSON 并推送到 Redis 队列，由 Backend 消费
        # 或者通过 HTTP POST 发送给 Backend API
        logger.debug(f"准备存储数据: {item.get('title', 'N/A')} | URL: {item.get('url')}")
        return item
