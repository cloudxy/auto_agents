"""租户上下文中间件（SaaS S1-3，T5 收紧 platform_scope 判定）

解析 Bearer JWT（只承身份）→ 注入 tenant_scope / platform_scope（ContextVar），
行级隔离（tenant_context.py 事件钩子）据此生效。无 token / 解析失败 → 不设作用域
（公开端点如 /health、/public/skills 走无上下文 legacy 语义：豁免表 + 无租户读）。

T5 决策 B 越权链收紧：platform_scope 仅 is_platform_admin 可入。旧条件
`is_platform_admin OR not tenant_id` 使 NULL 租户账号（公开注册历史产物）自动
获得平台态（跨租户全可见）——配合 024 收紧 NOT NULL 后合法用户不存在 NULL
tenant_id，有 token 而身份字段缺失/不合法 → 直接 401（堵死"NULL=平台态"放大器）。
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.utils.auth import decode_access_token
from platform_core.logger import get_logger
from platform_core.tenant_context import platform_scope, tenant_scope

logger = get_logger("middleware.tenant")


class TenantContextMiddleware(BaseHTTPMiddleware):
    """请求级租户作用域：平台超管 → platform_scope；租户用户 → tenant_scope"""

    @staticmethod
    def _reject() -> JSONResponse:
        """身份字段缺失/不合法的 401（格式对齐 ApiResponse/AuthenticationException）"""
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "code": "AUTH_FAILED",
                "message": "身份无效或已失效",
                "data": None,
                "request_id": None,
            },
        )

    async def dispatch(self, request: Request, call_next):
        auth = request.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.startswith("Bearer ") else ""
        payload = decode_access_token(token) if token else None
        if not payload:
            return await call_next(request)

        if payload.get("is_platform_admin"):
            with platform_scope():
                return await call_next(request)

        tenant_id = payload.get("tenant_id")
        if tenant_id is None:
            # 非平台超管且无租户归属：024 后合法用户不落此分支（迁移已回填全部
            # NULL 行 + register 挂 default），到达即旧 token/伪造 token
            logger.warning(f"拒绝无租户归属的非平台超管 token | sub={payload.get('sub')}")
            return self._reject()
        try:
            scoped_id = int(tenant_id)
        except (TypeError, ValueError):
            logger.warning(f"拒绝租户字段不合法 token | sub={payload.get('sub')}")
            return self._reject()
        with tenant_scope(scoped_id):
            return await call_next(request)
