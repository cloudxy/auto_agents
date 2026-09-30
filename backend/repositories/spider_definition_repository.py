"""爬虫定义数据访问层 - 封装所有 SpiderDefinition 相关的数据库操作（3.3）"""
from typing import List, Optional

from sqlalchemy import delete, or_, select
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

    async def get_by_name(
        self, name: str, tenant_id: Optional[int] = None,
    ) -> Optional[SpiderDefinition]:
        """按爬虫名查询定义（文件清单关联启停状态 / 启停端点定位用，4.4）

        审计 BUG-17：名字只在租户内唯一。调度 / 入队等平台态路径不带租户作用域，
        原先按名取行会取到别的租户的定义（连同它的 params）或 MultipleResultsFound
        被吞掉跳过校验——调用方须显式传 tenant_id；只取存活行。
        给定租户时：本租户的定义优先，其次平台级（tenant_id 为空）定义，绝不取别的租户的行。
        """
        stmt = select(SpiderDefinition).where(
            SpiderDefinition.name == name, SpiderDefinition.deleted_at.is_(None),
        )
        if tenant_id is not None:
            stmt = stmt.where(or_(
                SpiderDefinition.tenant_id == tenant_id, SpiderDefinition.tenant_id.is_(None),
            ))
            stmt = stmt.order_by(SpiderDefinition.tenant_id.is_(None).asc())
        stmt = stmt.order_by(SpiderDefinition.id.asc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def delete_if_unreferenced(self, name: str, tenant_id: Optional[int] = None) -> bool:
        """原子条件删除：仅当无 spider_tasks 引用时删除（m1 防 TOCTOU 并发绕过）

        DELETE ... AND NOT EXISTS 单语句原子判定，避免 get_by_name → count →
        delete 三步之间被并发入队绕过引用检查；以 rowcount 判定结果。
        返回 True=已删除；False=定义不存在或仍被引用（由调用方二次区分）。
        """
        # 审计 BUG-17：引用检查按定义所属租户关联（原先任何租户的同名任务都会挡住删除，
        # 等于把「别的租户在用这个名字」泄露出来）
        # 平台级定义（tenant_id 为空）被所有租户共用：任何租户的同名任务都算引用
        referenced = select(SpiderTask.id).where(
            SpiderTask.spider_name == name,
            or_(SpiderDefinition.tenant_id.is_(None), SpiderTask.tenant_id == SpiderDefinition.tenant_id),
        ).correlate(SpiderDefinition)
        stmt = delete(SpiderDefinition).where(SpiderDefinition.name == name, ~referenced.exists())
        if tenant_id is not None:
            stmt = stmt.where(SpiderDefinition.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return bool(result.rowcount)
