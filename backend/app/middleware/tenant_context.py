"""租户上下文中间件（SaaS S1-3，T5 收紧 platform_scope 判定；T12/F-01 DB 复核）

解析 Bearer JWT（只承身份）→ 注入 tenant_scope / platform_scope（ContextVar），
行级隔离（tenant_context.py 事件钩子）据此生效。无 token / 解析失败 → 不设作用域
（公开端点如 /health、/public/skills 走无上下文 legacy 语义：豁免表 + 无租户读）。

T5 决策 B 越权链收紧：platform_scope 仅 is_platform_admin 可入。旧条件
`is_platform_admin OR not tenant_id` 使 NULL 租户账号（公开注册历史产物）自动
获得平台态（跨租户全可见）——配合 024 收紧 NOT NULL 后合法用户不存在 NULL
tenant_id，有 token 而身份字段缺失/不合法 → 直接 401（堵死"NULL=平台态"放大器）。

F-01（重审收口）：claim 的 is_platform_admin 只承身份——进入 platform_scope 前
经 load_auth_identity 复核 DB 行（与 deps.get_current_user 同一加载函数、同一
快照，单一事实源）。撤销平台超管后存量 token 立即失去平台态：按 DB 行租户降级
tenant_scope（与 deps 守卫同源，双源一致）；查无此人/已停用/无租户归属/复核
异常 → 401（fail-closed，宁可拒绝不可放行越权）。复核快照挂
request.state.auth_identity 供 deps 直接消费（平台态请求每请求一次身份查询，
避免中间件/deps 双份）。
"""
from contextlib import asynccontextmanager

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.services.user_service import load_auth_identity
from backend.utils.auth import decode_access_token
from platform_core.db import get_async_db
from platform_core.logger import get_logger
from platform_core.tenant_context import platform_scope, tenant_scope

logger = get_logger("middleware.tenant")


@asynccontextmanager
async def _default_identity_session():
    """平台态复核会话（生产默认）：DBManager DEFAULT 引擎，短生命周期用毕即关

    与依赖注入的 get_async_db 同源；测试经 app.state.identity_session_factory
    覆写指向测试引擎（见 backend/tests/conftest.py 的 db_client fixture）。
    """
    agen = get_async_db()
    session = await agen.__anext__()
    try:
        yield session
    finally:
        await agen.aclose()


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

    async def _verify_platform_claim(self, request: Request, payload: dict):
        """平台态 DB 复核（F-01 单一事实源）：返回 AuthIdentity，None = fail-closed 拒绝

        复核发生在任何 scope 进入之前（无注入过滤，主键直查可见任意租户行）；
        快照挂 request.state.auth_identity，deps.get_current_user 优先消费。
        """
        user_id = payload.get("user_id")
        if not user_id:
            return None
        factory = getattr(request.app.state, "identity_session_factory", None) \
            or _default_identity_session
        try:
            async with factory() as session:
                identity = await load_auth_identity(session, user_id)
        except Exception as exc:  # noqa: BLE001 复核链路任何异常均按拒绝处理（fail-closed）
            logger.error(f"平台态复核失败（fail-closed 拒绝）| sub={payload.get('sub')} err={exc}")
            return None
        if identity is None or not identity.is_active:
            logger.warning(
                f"拒绝平台态 token：用户不存在或已停用 | sub={payload.get('sub')} user_id={user_id}")
            return None
        request.state.auth_identity = identity  # 同请求生命周期，deps 快照直用
        return identity

    async def dispatch(self, request: Request, call_next):
        auth = request.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.startswith("Bearer ") else ""
        payload = decode_access_token(token) if token else None
        if not payload:
            return await call_next(request)

        if payload.get("is_platform_admin"):
            identity = await self._verify_platform_claim(request, payload)
            if identity is None:
                return self._reject()
            if identity.is_platform_admin:
                with platform_scope():
                    return await call_next(request)
            # 撤销降级（F-01）：DB 行已非平台超管 → 按其租户进 tenant_scope
            # （deps 守卫消费同一快照，权限与隔离同步降级）；024 后合法行必有租户
            if identity.tenant_id is None:
                logger.warning(f"拒绝无租户归属的降级平台 token | sub={payload.get('sub')}")
                return self._reject()
            with tenant_scope(identity.tenant_id):
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
