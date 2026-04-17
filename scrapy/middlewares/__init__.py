"""Scrapy Middlewares - 高可用反爬与账号会话管理"""
import random
import hashlib
from platform_core.infra.log_init import get_logger
from scrapy.http import Cookies

logger = get_logger("spider")


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

        from scrapy.utils.session_manager import SessionManager
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
    """真实 UA 轮换中间件（仅针对未登录/无账号请求）"""
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
            
        ua = random.choice(self.USER_AGENTS)
        request.headers["User-Agent"] = ua
        return None


class ProxyMiddleware:
    """动态代理中间件 - 支持失效剔除"""
    def __init__(self):
        # TODO: 从配置或 API 获取代理列表
        self.proxies = [] 
        self.failed_proxies = set()

    def process_request(self, request, spider):
        if not self.proxies:
            return None
        
        available = [p for p in self.proxies if p not in self.failed_proxies]
        if not available:
            logger.warning("所有代理已失效，尝试直连")
            return None
            
        proxy = random.choice(available)
        request.meta["proxy"] = proxy
        return None

    def process_exception(self, request, exception, spider):
        proxy = request.meta.get("proxy")
        if proxy:
            self.failed_proxies.add(proxy)
            logger.warning(f"代理失效并剔除: {proxy} | Error: {str(exception)}")
        return None


class RetryMiddleware:
    """智能重试中间件 - 动态调整延迟"""
    def process_response(self, request, response, spider):
        if response.status in [429, 500, 502, 503, 504]:
            logger.warning(f"触发风控/服务器错误 [{response.status}]，准备重试: {request.url}")
            retry_req = request.copy()
            retry_req.dont_filter = True
            # 遇到 429 自动增加延迟
            if response.status == 429:
                retry_req.meta["download_delay"] = 5
            return retry_req
        return response


class FingerprintMiddleware:
    """请求指纹中间件 - 辅助去重"""
    def process_request(self, request, spider):
        # 生成唯一指纹，用于日志追踪
        fp = hashlib.md5(request.url.encode()).hexdigest()[:8]
        request.meta["fingerprint"] = fp
        return None
