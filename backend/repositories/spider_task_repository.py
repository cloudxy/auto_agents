"""爬虫任务数据访问层 - 封装所有 SpiderTask 相关的数据库操作"""
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.spider_task import SpiderTask
from platform_core.repository import BaseRepository


class SpiderTaskRepository(BaseRepository[SpiderTask]):
    """SpiderTask Repository —— 在 BaseRepository 之上扩展过滤/聚合"""

    def __init__(self, session: AsyncSession):
        super().__init__(model=SpiderTask, session=session)

    async def list_tasks(
        self,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
    ) -> List[SpiderTask]:
        """分页查询任务，可按状态过滤（最新优先）"""
        stmt = select(SpiderTask)
        if status:
            stmt = stmt.where(SpiderTask.status == status)
        stmt = stmt.order_by(SpiderTask.id.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, status: Optional[str] = None) -> int:
        """按状态计数（status=None 为总数）"""
        stmt = select(func.count(SpiderTask.id))
        if status:
            stmt = stmt.where(SpiderTask.status == status)
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def count_by_status(self) -> dict:
        """一次性返回各状态的计数（用于 /admin/stats）"""
        stmt = select(SpiderTask.status, func.count(SpiderTask.id)).group_by(SpiderTask.status)
        result = await self.session.execute(stmt)
        counts = {"pending": 0, "running": 0, "completed": 0, "failed": 0}
        for status, num in result.all():
            if status in counts:
                counts[status] = int(num)
        return counts
