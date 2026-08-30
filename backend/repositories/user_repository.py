"""用户数据访问层 - 封装所有 User 相关的数据库操作"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from platform_core.models.user import User
from platform_core.repository import BaseRepository


class UserRepository(BaseRepository[User]):
    """用户 Repository
    
    继承 BaseRepository，扩展用户特定的查询方法
    """
    
    def __init__(self, session: AsyncSession):
        super().__init__(model=User, session=session)
    
    async def get_by_username(self, username: str) -> Optional[User]:
        """根据用户名查询用户"""
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()
    
    async def get_by_email(self, email: str) -> Optional[User]:
        """根据邮箱查询用户"""
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
    
    async def exists_by_username(self, username: str) -> bool:
        """检查用户名是否存在"""
        return await self.exists(username=username)
    
    async def exists_by_email(self, email: str) -> bool:
        """检查邮箱是否存在"""
        return await self.exists(email=email)
    
    async def get_active_users(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> list[User]:
        """查询活跃用户列表"""
        result = await self.session.execute(
            select(User)
            .where(User.is_active == True)
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 20
    ) -> list[User]:
        """分页查询全部用户（最新优先，供用户管理页陈列）"""
        result = await self.session.execute(
            select(User)
            .order_by(User.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_users(self) -> int:
        """用户总数"""
        result = await self.session.execute(select(func.count(User.id)))
        return int(result.scalar() or 0)
