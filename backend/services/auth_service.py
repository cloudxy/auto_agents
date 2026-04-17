"""认证服务 - 业务逻辑层（只负责编排，不直接操作数据库）"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from backend.repositories.user_repository import UserRepository
from backend.utils.auth import verify_password, get_password_hash, create_access_token
from backend.cors.log_init import get_logger
from backend.app.exceptions import BusinessException
from pydantic import BaseModel

logger = get_logger("api")


class TokenResponse(BaseModel):
    """Token 响应（内部使用，不直接返回给前端）"""
    access_token: str
    token_type: str = "bearer"
    username: str
    is_admin: bool


class AuthService:
    """认证服务 - 业务逻辑编排
    
    职责：
    - 调用 Repository 进行数据存取
    - 执行业务规则验证
    - 协调多个 Repository 完成复杂业务
    
    注意：
    - 不直接写 SQL
    - 不直接访问 session.execute()
    - 所有数据库操作通过 Repository
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)  # 注入 UserRepository

    async def authenticate(self, username: str, password: str) -> Optional[dict]:
        """验证用户
        
        Returns:
            用户信息 dict，如果验证失败返回 None
        """
        logger.info(f"尝试验证用户: {username}")
        
        # 1. 通过 Repository 查询用户
        user = await self.user_repo.get_by_username(username)
        
        if not user:
            logger.warning(f"用户不存在: {username}")
            return None
        
        if not user.is_active:
            logger.warning(f"用户未激活: {username}")
            return None
        
        # 2. 验证密码
        if not verify_password(password, user.password_hash):
            logger.warning(f"密码错误: {username}")
            return None
        
        logger.info(f"用户认证成功: {username}")
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin
        }

    async def create_token(self, user_data: dict) -> TokenResponse:
        """创建访问令牌"""
        access_token = create_access_token(
            data={"sub": user_data["username"], "user_id": user_data["id"]}
        )
        
        logger.info(f"生成 Token | user={user_data['username']}")
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            username=user_data["username"],
            is_admin=user_data["is_admin"]
        )

    async def register_user(
        self,
        username: str,
        email: str,
        password: str,
        is_admin: bool = False
    ) -> dict:
        """注册用户
        
        Returns:
            新用户信息 dict
        """
        logger.info(f"注册新用户: {username}")
        
        # 1. 通过 Repository 检查唯一性
        if await self.user_repo.exists_by_username(username):
            raise BusinessException(
                message=f"用户名已存在: {username}",
                code="USERNAME_EXISTS",
                status_code=409
            )
        
        if await self.user_repo.exists_by_email(email):
            raise BusinessException(
                message=f"邮箱已被注册: {email}",
                code="EMAIL_EXISTS",
                status_code=409
            )
        
        # 2. 通过 Repository 创建用户
        hashed_password = get_password_hash(password)
        new_user = await self.user_repo.create(
            username=username,
            email=email,
            password_hash=hashed_password,
            is_admin=is_admin
        )
        
        await self.session.commit()  # 事务提交由 Service 控制
        
        logger.info(f"用户注册成功: {username}")
        return {
            "id": new_user.id,
            "username": new_user.username,
            "email": new_user.email
        }
