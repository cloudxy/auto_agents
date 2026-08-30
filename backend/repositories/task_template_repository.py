"""任务模板数据访问层 - 封装 TaskTemplate 的数据库操作"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.task_template import TaskTemplate
from platform_core.repository import BaseRepository


class TaskTemplateRepository(BaseRepository[TaskTemplate]):
    """TaskTemplate Repository —— 在 BaseRepository 之上扩展列表查询"""

    def __init__(self, session: AsyncSession):
        super().__init__(model=TaskTemplate, session=session)

    async def list_all(self, skip: int = 0, limit: int = 100) -> List[TaskTemplate]:
        """获取所有模板（按创建时间倒序）"""
        stmt = (
            select(TaskTemplate)
            .order_by(TaskTemplate.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> Optional[TaskTemplate]:
        """按名称查询（用于唯一性校验）"""
        stmt = select(TaskTemplate).where(TaskTemplate.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
