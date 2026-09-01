"""租户上下文中间件（SaaS S1-3）

解析 Bearer JWT（只承身份）→ 注入 tenant_scope / platform_scope（ContextVar），
行级隔离（tenant_context.py 事件钩子）据此生效。无 token / 解析失败 → 不设作用域
（公开端点如 /health、/public/skills 走无上下文 legacy 语义：豁免表 + 无租户读）。
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from backend.utils.auth import decode_access_token
from platform_core.logger import get_logger
from platform_core.tenant_context import platform_scope, tenant_scope

logger = get_logger("middleware.tenant")


class TenantContextMiddleware(BaseHTTPMiddleware):
    """请求级租户作用域：平台超管 → platform_scope；租户用户 → tenant_scope"""

    async def dispatch(self, request: Request, call_next):
        auth = request.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.startswith("Bearer ") else ""
        payload = decode_access_token(token) if token else None
        if not payload:
            return await call_next(request)

        tenant_id = payload.get("tenant_id")
        if payload.get("is_platform_admin") or not tenant_id:
            with platform_scope():
                return await call_next(request)
        with tenant_scope(int(tenant_id)):
            return await call_next(request)
