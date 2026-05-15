"""认证路由 - 使用统一参数接收器和响应格式"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from platform_core.db import get_async_db
from backend.services.auth_service import AuthService
from platform_core.logger import get_logger
from platform_core.db import redis_client
from platform_core.exceptions import AuthenticationException, RateLimitException
from platform_core.schemas import LoginRequest, RegisterRequest  # 统一参数接收器
from backend.app.responses import ApiResponse, ok

logger = get_logger("api")

router = APIRouter(prefix="/auth", tags=["认证"])


async def check_login_rate_limit(username: str):
    """检查登录频率限制（每用户 15 分钟内最多 5 次失败）"""
    redis = redis_client()
    key = f"login_fail:{username}"
    
    fail_count = await redis.get(key)
    if fail_count and int(fail_count) >= 5:
        ttl = await redis.ttl(key)
        raise RateLimitException(
            message=f"登录失败次数过多，请{ttl // 60}分钟后再试",
            retry_after=ttl
        )


async def record_login_failure(username: str):
    """记录登录失败（Redis 计数器）"""
    redis = redis_client()
    key = f"login_fail:{username}"
    
    await redis.incr(key)
    await redis.expire(key, 900)  # 15 分钟过期


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
            "is_admin": token_response.is_admin
        },
        message="登录成功"
    )


@router.get("/permissions", response_model=ApiResponse)
async def get_permissions(db: AsyncSession = Depends(get_async_db)):
    """获取当前用户的权限列表"""
    # 简化实现：根据 token 中的信息（由于没有中间件设置 request.user，这里模拟从 db 获取，或根据 token 判断）
    # 实际项目中应有专门的依赖获取当前用户
    # 暂时模拟返回
    return ok(data=[
        'menu:dashboard', 'menu:spiders', 'menu:spiders.tasks', 'menu:spiders.logs', 
        'menu:users', 'menu:data', 'menu:settings', 'btn:create', 'btn:delete'
    ])
@router.post("/register", response_model=ApiResponse)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """用户注册
    
    Args:
        request: 注册请求（自动验证 username/email/password）
        db: 数据库会话
    
    Returns:
        ApiResponse: 包含 user_id 的响应
    """
    logger.info(f"注册请求 | username={request.username}")
    
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
