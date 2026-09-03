"""请求 ID 中间件 - 为每个请求生成唯一 ID，用于链路追踪（B4：同步 bind loguru）"""
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from platform_core.logger import get_logger

logger = get_logger("request")

# loguru 全局默认 extra：未绑定上下文的日志行 request_id 显示 "-"（B4）
logger.configure(extra={"request_id": "-"})


class RequestIDMiddleware(BaseHTTPMiddleware):
    """为每个请求生成唯一 request_id：注入 request.state + 响应头 + loguru 上下文

    contextualize 基于 contextvars：请求任务内所有日志（service/repository 层）
    自动携带 request_id，错误日志与 X-Request-ID 响应头全链路可关联。
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id

        with logger.contextualize(request_id=request_id):
            response = await call_next(request)

        response.headers["X-Request-ID"] = request_id
        return response
