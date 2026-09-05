"""认证服务 - 业务逻辑层（只负责编排，不直接操作数据库）"""
import asyncio
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from backend.repositories.user_repository import UserRepository
from backend.utils.auth import verify_password, get_password_hash, create_access_token
from platform_core.logger import get_logger
from platform_core.exceptions import BusinessException
from pydantic import BaseModel

logger = get_logger("api")

# 用户不存在时的哑哈希（P1-9）：做一次等代价 bcrypt 校验对齐时序，
# 消除"用户名存在与否"的响应时间差（用户枚举侧信道）
_DUMMY_HASH = get_password_hash("timing-equalization-dummy-password")


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
        """验证用户（T5 决策 A：多行候选 + 密码消歧）

        跨租户同名是产品既定能力（各企业各建"张三"），get_by_username 返回
        全部候选行；凭据即身份——逐行验密码，唯一命中者胜出：
        - 0 行：哑哈希对齐时序 → None（P1-9 保留）；
        - 1 行：照常验证；
        - 多行：唯一命中胜出；多行皆中/皆不中 → None。401 文案不泄露命中数
          （"多中"本身即账号枚举信号）。

        Returns:
            用户信息 dict，如果验证失败返回 None
        """
        logger.info(f"尝试验证用户: {username}")

        # 1. 通过 Repository 查询全部候选（跨租户口径见 get_by_username R13 声明）
        candidates = await self.user_repo.get_by_username(username)

        if not candidates:
            # 时序对齐（P1-9）：对不存在的用户做一次等代价哈希校验
            await asyncio.to_thread(verify_password, password, _DUMMY_HASH)
            logger.warning(f"用户不存在: {username}")
            return None

        candidates = [u for u in candidates if u.is_active]
        if not candidates:
            logger.warning(f"用户均已停用或被软删: {username}")
            return None

        # 2. 密码消歧（P1-9：bcrypt 是同步 CPU 密集操作，转线程池避免阻塞事件循环）
        matched = [
            u for u in candidates
            if await asyncio.to_thread(verify_password, password, u.password_hash)
        ]
        if len(matched) != 1:
            # 皆不中（密码错误）/ 多行皆中（同密码重复名，凭据无法消歧）一律 401
            logger.warning(f"密码消歧失败: {username}")
            return None
        user = matched[0]

        logger.info(f"用户认证成功: {username}")
        role = getattr(user, "role", None)
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin,
            "role": role or ("admin" if user.is_admin else "operator"),
            # 租户/平台维度（与 JWT payload 同源）：中间件平台态判定 + 前端菜单可见性
            "tenant_id": getattr(user, "tenant_id", None),
            "tenant_role": getattr(user, "tenant_role", None),
            "is_platform_admin": bool(getattr(user, "is_platform_admin", False)),
        }

    async def create_token(self, user_data: dict) -> TokenResponse:
        """创建访问令牌"""
        # S1-3：claims 只承身份——tenant_id/tenant_role/is_platform_admin 随行携带；
        # role 仅为兼容存量消费方保留，权限判定一律 DB 快照重算
        access_token = create_access_token(
            data={
                "sub": user_data["username"],
                "user_id": user_data["id"],
                "role": user_data.get("role", "operator"),
                "tenant_id": user_data.get("tenant_id"),
                "tenant_role": user_data.get("tenant_role"),
                "is_platform_admin": bool(user_data.get("is_platform_admin", False)),
            }
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
        """注册用户（T5 决策 B：挂 default 租户，不再产生 NULL 租户行）

        users.tenant_id 已收紧 NOT NULL（迁移 024）——公开注册一律归属
        default 租户（tenant_role=viewer），NULL 租户账号的历史放大器
        （NULL 兜底平台态）随之消灭。

        Returns:
            新用户信息 dict
        """
        logger.info(f"注册新用户: {username}")

        # default 租户兜底归属（017 种子保证存在；缺失即环境未初始化）
        from sqlalchemy import select

        from platform_core.models.tenant import Tenant

        tenant = (await self.session.execute(
            select(Tenant).where(Tenant.slug == "default")
        )).scalar_one_or_none()
        if tenant is None:
            logger.error("default 租户缺失，公开注册不可用（迁移 017 未执行？）")
            raise BusinessException(
                message="注册服务暂不可用，请稍后再试",
                code="REGISTER_UNAVAILABLE",
                status_code=503
            )

        # 1. 唯一性检查：username 按 (default 租户, username) 口径（含软删行，
        #    与 (tenant_id, username) 唯一约束及 T4 占位口径一致）；email 全局唯一
        if await self.user_repo.exists_username_in_tenant(tenant.id, username):
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

        # 2. 通过 Repository 创建用户（哈希计算转线程池，P1-9）
        hashed_password = await asyncio.to_thread(get_password_hash, password)
        new_user = await self.user_repo.create(
            username=username,
            email=email,
            password_hash=hashed_password,
            is_admin=is_admin,
            tenant_id=tenant.id,
            tenant_role="viewer",
        )

        await self.session.commit()  # 事务提交由 Service 控制
        # commit 后实例过期，必须 refresh 再读属性（否则异步上下文惰性加载抛 MissingGreenlet）
        await self.session.refresh(new_user)

        logger.info(f"用户注册成功: {username} tenant=default({tenant.id})")
        return {
            "id": new_user.id,
            "username": new_user.username,
            "email": new_user.email
        }
