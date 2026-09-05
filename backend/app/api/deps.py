"""API 鉴权依赖 - JWT 解析 + 角色守卫（RBAC）

角色层级：
- admin    全权（用户/配置/删除/调度管理）
- operator 操作（运行任务、创建任务，不可删除与改配置）
- viewer   只读（查询类接口）

is_admin=True 的存量用户等价 admin 角色。
"""
from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.user_service import load_auth_identity
from backend.utils.auth import decode_access_token
from platform_core.db import get_async_db
from platform_core.exceptions import AuthenticationException, AuthorizationException
from platform_core.logger import get_logger

logger = get_logger("api")

_bearer = HTTPBearer(auto_error=False)

ROLE_ALL = ("admin", "operator", "viewer")


@dataclass(frozen=True)
class CurrentUser:
    """当前登录用户快照（鉴权时固化）

    历史坑（ADR-0007 已收口）：路由层 session.commit() 会使 ORM 对象属性全部
    过期，再读 user.id/username 会触发同步惰性加载，异步上下文抛
    MissingGreenlet——事务所有权已唯一归属 Service 层（快照先于提交），
    API 层不再碰 session 生命周期，本快照型返回值是既定防线的组成部分。

    S1-3 租户身份（claims 只承身份，权限一律 DB 快照重算）：
    is_platform_admin=True → 平台超管（platform_scope；T5 后 DB 行挂 platform
    租户，claims 的 tenant_id 可能为 None——旧 token 形态兼容）；
    否则租户用户（tenant_scope，tenant_role: owner/admin/operator/viewer）。
    """

    id: int
    username: str
    role: str
    tenant_id: int | None = None
    tenant_role: str | None = None
    is_platform_admin: bool = False


def effective_role(user) -> str:
    """生效角色：历史 is_admin 标记等价 admin；未知/空角色按最小权限 viewer（B1）

    T1 收口（R7）：入参为鉴权身份快照（经 services.user_service.load_auth_identity
    取得的 AuthIdentity，duck-typed 只读 is_admin/role 两属性），API 层不 import ORM。
    """
    if user.is_admin:
        return "admin"
    return user.role or "viewer"


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_async_db),
) -> CurrentUser:
    """解析 Bearer Token 并加载当前用户，返回属性快照（缺失/无效/停用均抛 401）

    F-01 单一事实源：身份加载统一走 services.user_service.load_auth_identity；
    中间件平台态复核已挂载的快照（request.state.auth_identity，同请求生命周期）
    直接消费——平台态请求每请求一次身份查询，避免中间件/deps 双份。
    """
    logger.debug("校验请求身份")
    if credentials is None or not credentials.credentials:
        raise AuthenticationException(message="未登录或缺少 Token")
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise AuthenticationException(message="Token 无效或已过期")
    user_id = payload.get("user_id")
    if not user_id:
        raise AuthenticationException(message="Token 缺少用户信息")
    identity = getattr(request.state, "auth_identity", None)
    if identity is None:
        identity = await load_auth_identity(session, user_id)
    if identity is None or not identity.is_active:
        raise AuthenticationException(message="用户不存在或已停用")
    # claims 只承身份：权限/租户字段一律从 DB 行快照取（load_auth_identity），
    # 禁用/降级立即生效，防 token 生命周期内权限漂移（S2 短窗失效验收的前提）
    return CurrentUser(
        id=identity.id,
        username=identity.username,
        role=effective_role(identity),
        tenant_id=identity.tenant_id,
        tenant_role=identity.tenant_role,
        is_platform_admin=identity.is_platform_admin,
    )


def require_role(*roles: str) -> Callable:
    """角色守卫依赖工厂：命中任一角色放行，否则 403"""

    async def _guard(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            logger.warning(f"权限不足被拒绝 | user={user.username} role={user.role} need={roles}")
            raise AuthorizationException(message=f"需要角色 {('/'.join(roles))}，当前为 {user.role}")
        return user

    return _guard


# 常用守卫快捷实例
require_login = require_role(*ROLE_ALL)      # 任意已登录角色
require_operator = require_role("admin", "operator")
require_admin = require_role("admin")


async def require_platform_admin(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """平台级守卫：仅 is_platform_admin（tenant_id 恒 NULL 的平台超管）"""
    if not user.is_platform_admin:
        raise AuthorizationException(message="需要平台管理员权限")
    return user
