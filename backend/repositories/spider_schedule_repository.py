"""爬虫定时调度数据访问层 - 封装所有 SpiderSchedule 相关的数据库操作"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.spider_schedule import SpiderSchedule
from platform_core.repository import BaseRepository


class SpiderScheduleRepository(BaseRepository[SpiderSchedule]):
    """SpiderSchedule Repository —— 在 BaseRepository 之上扩展到期扫描/过滤"""

    def __init__(self, session: AsyncSession):
        super().__init__(model=SpiderSchedule, session=session)

    async def list_all(self) -> List[SpiderSchedule]:
        """全量列表（调度计划数量有限，不分页；最新优先）"""
        stmt = select(SpiderSchedule).order_by(SpiderSchedule.id.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        """计划总数"""
        stmt = select(func.count(SpiderSchedule.id))
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def list_due(self, now: datetime) -> List[SpiderSchedule]:
        """到期扫描：启用且 next_run_at <= now 的计划（调度器每轮调用）"""
        stmt = (
            select(SpiderSchedule)
            .where(SpiderSchedule.enabled.is_(True))
            .where(SpiderSchedule.next_run_at <= now)
            .order_by(SpiderSchedule.next_run_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_spider(self, spider_name: str) -> Optional[SpiderSchedule]:
        """按爬虫名查找计划（同爬虫仅允许一个调度计划）"""
        stmt = select(SpiderSchedule).where(SpiderSchedule.spider_name == spider_name)
        result = await self.session.execute(stmt)
        return result.scalars().first()
