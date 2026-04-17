"""请求耗时中间件 - 记录每个请求的处理时间"""
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from platform_core.infra.log_init import get_logger

logger = get_logger("api")


class ProcessTimeMiddleware(BaseHTTPMiddleware):
    """记录每个请求的处理耗时，注入到响应头"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        response = await call_next(request)
        
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.3f}s"
        
        # 慢请求告警（超过 2 秒）
        if process_time > 2.0:
            logger.warning(
                f"慢请求 | path={request.url.path} | "
                f"method={request.method} | time={process_time:.3f}s"
            )
        
        return response
