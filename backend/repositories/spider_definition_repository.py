"""爬虫定义数据访问层 - 封装所有 SpiderDefinition 相关的数据库操作（3.3）"""
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.spider_definition import SpiderDefinition
from platform_core.models.spider_task import SpiderTask
from platform_core.repository import BaseRepository


class SpiderDefinitionRepository(BaseRepository[SpiderDefinition]):
    """SpiderDefinition Repository —— 注册表元数据的 DB 数据源"""

    def __init__(self, session: AsyncSession):
        super().__init__(model=SpiderDefinition, session=session)

    async def list_enabled(self) -> List[SpiderDefinition]:
        """启用的爬虫定义（注册表下发清单，按 id 稳定排序）"""
        stmt = (
            select(SpiderDefinition)
            .where(SpiderDefinition.enabled.is_(True))
            .order_by(SpiderDefinition.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> Optional[SpiderDefinition]:
        """按爬虫名查询定义（文件清单关联启停状态 / 启停端点定位用，4.4）"""
        stmt = select(SpiderDefinition).where(SpiderDefinition.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_if_unreferenced(self, name: str) -> bool:
        """原子条件删除：仅当无 spider_tasks 引用时删除（m1 防 TOCTOU 并发绕过）

        DELETE ... AND NOT EXISTS 单语句原子判定，避免 get_by_name → count →
        delete 三步之间被并发入队绕过引用检查；以 rowcount 判定结果。
        返回 True=已删除；False=定义不存在或仍被引用（由调用方二次区分）。
        """
        stmt = delete(SpiderDefinition).where(
            SpiderDefinition.name == name,
            ~select(SpiderTask.id).where(SpiderTask.spider_name == name).exists(),
        )
        result = await self.session.execute(stmt)
        return bool(result.rowcount)
