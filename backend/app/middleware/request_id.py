"""请求 ID 中间件 - 为每个请求生成唯一 ID，用于链路追踪"""
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIDMiddleware(BaseHTTPMiddleware):
    """为每个请求生成唯一 request_id，并注入到 request.state"""

    async def dispatch(self, request: Request, call_next):
        # 优先使用客户端传入的 X-Request-ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:16]
        
        # 注入到 request.state
        request.state.request_id = request_id
        
        # 执行请求
        response = await call_next(request)
        
        # 在响应头中返回 request_id
        response.headers["X-Request-ID"] = request_id
        
        return response
