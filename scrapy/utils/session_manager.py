"""Scrapy Utils - 账号会话持久化管理器 (Sync Version)"""
import json
from utils.redis_client import redis_client
from platform_core.logger import get_logger

logger = get_logger("spider")

class SessionManager:
    """
    管理爬虫账号的登录态、Cookie 和指纹信息。
    适配 Scrapy 同步环境，使用 Redis 同步客户端。
    """
    
    def __init__(self, account_id: str):
        self.account_id = account_id
        self.redis_key = f"session:{account_id}"
        self.r = redis_client()

    def save_session(self, cookies: dict, headers: dict = None, ua: str = None):
        """保存登录后的会话信息"""
        session_data = {
            "cookies": json.dumps(cookies),
            "headers": json.dumps(headers or {}),
            "ua": ua,
            "is_logged_in": "True"
        }
        self.r.hset(self.redis_key, mapping=session_data)
        logger.info(f"账号 [{self.account_id}] 会话已持久化到 Redis")

    def get_session(self) -> dict:
        """获取当前账号的会话信息"""
        data = self.r.hgetall(self.redis_key)
        if not data:
            return {}
        
        # 解析 JSON 字符串
        try:
            return {
                "cookies": json.loads(data.get(b'cookies', b'{}')),
                "headers": json.loads(data.get(b'headers', b'{}')),
                "ua": data.get(b'ua', b'').decode(),
                "is_logged_in": data.get(b'is_logged_in', b'False').decode() == "True"
            }
        except Exception as e:
            logger.error(f"解析会话数据失败: {e}")
            return {}

    def invalidate(self):
        """标记会话失效（触发重新登录）"""
        self.r.hset(self.redis_key, "is_logged_in", "False")
        logger.warning(f"账号 [{self.account_id}] 会话已标记为失效")

    def is_valid(self) -> bool:
        """检查会话是否有效"""
        status = self.r.hget(self.redis_key, "is_logged_in")
        return status == b"True"
