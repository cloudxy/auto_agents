"""认证路由 - 登录 / 注册 / 权限查询（使用 Schema 参数接收器 + ApiResponse 统一响应）

限流计数器统一走异步 Redis 门面 get_async_redis（期 3 收口：登录/注册路径
此前直调同步 redis_client 阻塞事件循环，注释自证历史误用）。

fail-open 约定（任务 #35 显式化）：限流是可用性加固而非安全闸门，Redis 故障
（RedisError）时检查放行、计数跳过——只捕获 RedisError，其他异常照常冒泡。
"""
from fastapi import APIRouter, Depends, Request
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession
from platform_core.db import get_async_db
from backend.services.auth_service import AuthService
from backend.app.api.deps import CurrentUser, get_current_user
from platform_core.logger import get_logger
from platform_core.redis_async import get_async_redis
from platform_core.exceptions import AuthenticationException, RateLimitException
from platform_core.schemas import LoginRequest, RegisterRequest  # 统一参数接收器
from backend.app.responses import ApiResponse, ok

logger = get_logger("api")

router = APIRouter(prefix="/auth", tags=["认证"])


async def check_login_rate_limit(username: str):
    """检查登录频率限制（每用户 15 分钟内最多 5 次失败）

    fail-open：Redis 故障时放行登录（不因限流基础设施故障阻断用户）。
    """
    redis = get_async_redis()
    key = f"login_fail:{username}"

    try:
        fail_count = await redis.get(key)
        if fail_count and int(fail_count) >= 5:
            ttl = await redis.ttl(key)
            raise RateLimitException(
                message=f"登录失败次数过多，请{ttl // 60}分钟后再试",
                retry_after=ttl
            )
    except RedisError:
        logger.warning(f"登录限流检查失败，fail-open 放行 | key={key}")


async def record_login_failure(username: str):
    """记录登录失败（Redis 计数器，pipeline 原子提交）

    与 record_register_attempt 同构：INCR+EXPIRE 两次独立往返改为 pipeline
    原子提交，消除两步之间进程崩溃留下的无 TTL 永久计数器（用户名被永久 429）。
    fail-open：Redis 故障时跳过计数（失败路径不因基础设施故障 500）。
    """
    redis = get_async_redis()
    key = f"login_fail:{username}"

    try:
        pipe = redis.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, 900)  # 15 分钟过期（与 check 窗口一致）
        await pipe.execute()
    except RedisError:
        logger.warning(f"登录失败计数写入失败，跳过计数 | key={key}")


# 注册限流（防批量注册滥用）：与 login_fail 同构的 Redis 计数器模式，
# 按来源 IP 限制（注册不存在"失败重试"语义，成功失败均计数）
_REGISTER_WINDOW_SECONDS = 900   # 15 分钟窗口（与 login_fail 一致）
_REGISTER_MAX_ATTEMPTS = 5       # 每窗口每 IP 最多 5 次注册请求


async def check_register_rate_limit(client_ip: str):
    """检查注册频率限制（每 IP 15 分钟内最多 5 次注册请求，模式与 login 限流一致）

    fail-open：与 check_login_rate_limit 一致，Redis 故障时放行。
    """
    redis = get_async_redis()
    key = f"register_fail:{client_ip}"

    try:
        attempt_count = await redis.get(key)
        if attempt_count and int(attempt_count) >= _REGISTER_MAX_ATTEMPTS:
            ttl = await redis.ttl(key)
            raise RateLimitException(
                message=f"注册请求过于频繁，请{ttl // 60}分钟后再试",
                retry_after=ttl
            )
    except RedisError:
        logger.warning(f"注册限流检查失败，fail-open 放行 | key={key}")


async def record_register_attempt(client_ip: str):
    """记录一次注册请求（Redis 计数器）

    m-4 评审修复：INCR+EXPIRE 两次独立往返改为 pipeline 原子提交。
    原写法在两步之间进程崩溃 / 连接中断时会留下无 TTL 的永久计数器，
    累计到阈值后该 IP 被永久限流（只能手工清键）；pipeline 保证
    INCR 与 EXPIRE 同批提交，窗口计数始终带过期时间。
    fail-open：Redis 故障时跳过计数（注册主流程不因限流基础设施故障 500）。
    """
    redis = get_async_redis()
    key = f"register_fail:{client_ip}"

    try:
        pipe = redis.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, _REGISTER_WINDOW_SECONDS)
        await pipe.execute()
    except RedisError:
        logger.warning(f"注册计数写入失败，跳过计数 | key={key}")


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
_ROLE_PERMISSIONS = {
    "viewer": [
        'menu:dashboard', 'menu:spiders', 'menu:spiders.tasks', 'menu:spiders.logs',
    ],
    "operator": [
        'menu:dashboard', 'menu:spiders', 'menu:spiders.tasks', 'menu:spiders.logs',
        'menu:data', 'btn:create',
    ],
    "admin": [
        'menu:dashboard', 'menu:spiders', 'menu:spiders.tasks', 'menu:spiders.logs',
        'menu:users', 'menu:data', 'menu:settings', 'btn:create', 'btn:delete',
        'btn:schedule', 'menu:ai', 'menu:logs', 'menu:llm', 'menu:newapi',
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
