"""认证路由 - 登录 / 注册 / 权限查询（使用 Schema 参数接收器 + ApiResponse 统一响应）

限流计数器统一走异步 Redis 门面 get_async_redis（期 3 收口：登录/注册路径
此前直调同步 redis_client 阻塞事件循环，注释自证历史误用）。

fail-open 约定（任务 #35 显式化）：限流是可用性加固而非安全闸门，Redis 故障
（RedisError）时检查放行、计数跳过——只捕获 RedisError，其他异常照常冒泡。
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from platform_core.db import get_async_db
from backend.services.auth_service import AuthService
from backend.app.api.deps import CurrentUser, get_current_user
from platform_core.logger import get_logger
from platform_core.redis_async import get_async_redis
from backend.app.core.rate_limiter import (
    LOGIN_FAIL_POLICY, REGISTER_ATTEMPT_POLICY, check_rate_limit, record_attempt,
)
from platform_core.exceptions import AuthenticationException
from platform_core.schemas import LoginRequest, RegisterRequest  # 统一参数接收器
from backend.app.responses import ApiResponse, ok

logger = get_logger("api")

router = APIRouter(prefix="/auth", tags=["认证"])


async def check_login_rate_limit(username: str):
    """检查登录频率限制（每用户 15 分钟内最多 5 次失败；策略见 rate_limiter.LOGIN_FAIL_POLICY）"""
    redis = get_async_redis()
    await check_rate_limit(redis, LOGIN_FAIL_POLICY, username)


async def record_login_failure(username: str):
    """记录登录失败（pipeline 原子计数；策略见 rate_limiter.LOGIN_FAIL_POLICY）"""
    redis = get_async_redis()
    await record_attempt(redis, LOGIN_FAIL_POLICY, username)


async def check_register_rate_limit(client_ip: str):
    """检查注册频率限制（每 IP 15 分钟 5 次；策略见 rate_limiter.REGISTER_ATTEMPT_POLICY）"""
    redis = get_async_redis()
    await check_rate_limit(redis, REGISTER_ATTEMPT_POLICY, client_ip)


async def record_register_attempt(client_ip: str):
    """记录一次注册请求（pipeline 原子计数；策略见 rate_limiter.REGISTER_ATTEMPT_POLICY）"""
    redis = get_async_redis()
    await record_attempt(redis, REGISTER_ATTEMPT_POLICY, client_ip)


@router.post("/login", response_model=ApiResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_async_db)):
    """用户登录
    
    Args:
        request: 登录请求（自动验证 username/password）
        db: 数据库会话
    
    Returns:
        ApiResponse: 包含 access_token 的响应
    """
    logger.info(f"登录请求 | username={request.username}")
    
    # 检查频率限制
    await check_login_rate_limit(request.username)
    
    auth_service = AuthService(db)
    user_data = await auth_service.authenticate(request.username, request.password)
    
    if not user_data:
        # 记录失败次数
        await record_login_failure(request.username)
        raise AuthenticationException(message="用户名或密码错误")
    
    token_response = await auth_service.create_token(user_data)
    
    return ok(
        data={
            "access_token": token_response.access_token,
            "token_type": token_response.token_type,
            "username": token_response.username,
            "is_admin": token_response.is_admin,
            "role": user_data.get("role", "operator")
        },
        message="登录成功"
    )


# 角色 → 权限映射（前端按此控制菜单/按钮可见性，后端守卫为最终防线）
# 权限单真相源（R5）：前端登录后从 /permissions 读取，不再硬编码
_ROLE_PERMISSIONS = {
    "viewer": [
        'menu:dashboard', 'menu:spiders', 'menu:spiders.tasks', 'menu:spiders.logs',
        'menu:ai', 'menu:skills', 'menu:members', 'menu:usage',
    ],
    "operator": [
        'menu:dashboard', 'menu:spiders', 'menu:spiders.tasks', 'menu:spiders.logs',
        'menu:data', 'menu:ai', 'menu:skills', 'menu:members', 'menu:usage',
        'btn:create', 'btn:skill:edit',
    ],
    "admin": [
        'menu:dashboard', 'menu:spiders', 'menu:spiders.tasks', 'menu:spiders.logs',
        'menu:users', 'menu:data', 'menu:settings', 'menu:ai', 'menu:skills',
        'menu:members', 'menu:usage', 'menu:platform-ops', 'menu:logs',
        'menu:llm', 'menu:newapi',
        'btn:create', 'btn:delete', 'btn:schedule', 'btn:skill:edit', 'btn:skill:admin',
    ],
}


@router.get("/permissions", response_model=ApiResponse)
async def get_permissions(user: CurrentUser = Depends(get_current_user)):
    """获取当前用户的权限列表（按角色动态返回，角色已在鉴权时快照）"""
    logger.info(f"查询权限 | user={user.username} role={user.role}")
    return ok(data=_ROLE_PERMISSIONS.get(user.role, _ROLE_PERMISSIONS["viewer"]))
@router.post("/register", response_model=ApiResponse)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_async_db),
    http_request: Request = None,
):
    """用户注册
    
    Args:
        request: 注册请求（自动验证 username/email/password）
        db: 数据库会话
        http_request: 原始请求（取来源 IP 做限流维度）
    
    Returns:
        ApiResponse: 包含 user_id 的响应
    """
    logger.info(f"注册请求 | username={request.username}")
    client_ip = (http_request.client.host if http_request and http_request.client else "unknown")
    # 检查注册频率限制（请求到达即计数，成功失败均计入防刷）
    await check_register_rate_limit(client_ip)
    await record_register_attempt(client_ip)
    
    auth_service = AuthService(db)
    user = await auth_service.register_user(
        username=request.username,
        email=request.email,
        password=request.password,
        is_admin=False  # 默认非管理员
    )
    
    return ok(
        data={"user_id": user["id"]},
        message="注册成功"
    )
