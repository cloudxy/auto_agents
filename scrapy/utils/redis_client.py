"""
Scrapy 侧 Redis 客户端 —— 直接读 config.settings.REDIS.DEFAULT.URL

设计约束：
- 爬虫侧不初始化 DBManager（避免触发 MySQL 连接）
- 使用 decode_responses=True 便于 session_manager 直接处理字符串
- 连接懒加载，按需建立
"""
import redis
from config import settings

_redis_client = None


def redis_client():
    """返回共享的同步 Redis 客户端（懒加载）"""
    global _redis_client
    if _redis_client is None:
        url = settings.REDIS.DEFAULT.URL
        _redis_client = redis.from_url(url, decode_responses=True, socket_keepalive=True)
    return _redis_client
