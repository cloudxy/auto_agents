"""用户管理服务 - 业务逻辑编排层

职责：
- 用户列表查询（管理后台用户管理页）
- 所有数据库操作通过 Repository，不直接写 SQL
"""
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.user_repository import UserRepository
from platform_core.logger import get_logger
from platform_core.schemas.auth import UserListResponse, UserResponse

logger = get_logger("api")


class UserService:
    """用户管理编排"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = UserRepository(session)

    async def list_users(self, skip: int = 0, limit: int = 20) -> UserListResponse:
        """分页查询用户（Service 层负责把 ORM 实体转成响应契约）"""
        logger.info(f"查询用户列表: skip={skip}, limit={limit}")
        items = await self.repo.list_users(skip=skip, limit=limit)
        total = await self.repo.count_users()
        return UserListResponse(
            total=total,
            items=[UserResponse.model_validate(u) for u in items],
        )
