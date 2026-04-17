"""Scrapy Utils - 账号会话持久化管理器"""
import json
from core.db_init import redis_client
from core.log_init import get_logger

logger = get_logger("spider")

class SessionManager:
    """
    管理爬虫账号的登录态、Cookie 和指纹信息。
    所有数据持久化在 Redis 中，支持多进程/分布式共享。
    """
    
    def __init__(self, account_id: str):
        self.account_id = account_id
        self.redis_key = f"session:{account_id}"
        self.r = redis_client()

    async def save_session(self, cookies: dict, headers: dict = None, ua: str = None):
        """保存登录后的会话信息"""
        session_data = {
            "cookies": cookies,
            "headers": headers or {},
            "ua": ua,
            "is_logged_in": True
        }
        await self.r.hset(self.redis_key, mapping=session_data)
        logger.info(f"账号 [{self.account_id}] 会话已持久化到 Redis")

    async def get_session(self) -> dict:
        """获取当前账号的会话信息"""
        data = await self.r.hgetall(self.redis_key)
        if not data:
            return {}
        
        # 解码 Redis 返回的 bytes
        return {k.decode(): v.decode() for k, v in data.items()}

    async def invalidate(self):
        """标记会话失效（触发重新登录）"""
        await self.r.hset(self.redis_key, "is_logged_in", "False")
        logger.warning(f"账号 [{self.account_id}] 会话已标记为失效")

    async def is_valid(self) -> bool:
        """检查会话是否有效"""
        status = await self.r.hget(self.redis_key, "is_logged_in")
        return status == b"True" if status else False
