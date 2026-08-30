"""API 鉴权依赖 - JWT 解析 + 角色守卫（RBAC）

角色层级：
- admin    全权（用户/配置/删除/调度管理）
- operator 操作（运行任务、创建任务，不可删除与改配置）
- viewer   只读（查询类接口）

is_admin=True 的存量用户等价 admin 角色。
"""
from dataclasses import dataclass
from typing import Callable

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.utils.auth import decode_access_token
from platform_core.db import get_async_db
from platform_core.exceptions import AuthenticationException, AuthorizationException
from platform_core.logger import get_logger
from platform_core.models.user import User

logger = get_logger("api")

_bearer = HTTPBearer(auto_error=False)

ROLE_ALL = ("admin", "operator", "viewer")


@dataclass(frozen=True)
class CurrentUser:
    """当前登录用户快照（鉴权时固化）

    后续路由若发生 session.commit()，ORM 对象属性会全部过期；
    届时再读 user.id/username 会触发同步惰性加载，异步上下文抛 MissingGreenlet。
    """

    id: int
    username: str
    role: str


def effective_role(user: User) -> str:
    """生效角色：历史 is_admin 标记等价 admin"""
    if user.is_admin:
        return "admin"
    return user.role or "operator"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_async_db),
) -> CurrentUser:
    """解析 Bearer Token 并加载当前用户，返回属性快照（缺失/无效/停用均抛 401）"""
    logger.debug("校验请求身份")
    if credentials is None or not credentials.credentials:
        raise AuthenticationException(message="未登录或缺少 Token")
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise AuthenticationException(message="Token 无效或已过期")
    user_id = payload.get("user_id")
    if not user_id:
        raise AuthenticationException(message="Token 缺少用户信息")
    user = await session.get(User, user_id)
    if not user or not user.is_active:
        raise AuthenticationException(message="用户不存在或已停用")
    return CurrentUser(id=user.id, username=user.username, role=effective_role(user))


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
