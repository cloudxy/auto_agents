"""平台核心 - 通用数据访问层 (Base Repository)

软删除感知（DB 升级 2026-09 Phase A / DB-03）：
- 模型含 deleted_at（SoftDeleteMixin）时，get_by_id/get_all 自动过滤已删行
- soft_delete/restore 走 UPDATE 而非 DELETE；get_all_with_deleted 供管理视角
- 无 SoftDeleteMixin 的表（审计/历史/子表/聚合/系统）行为与升级前完全一致
"""
from typing import Type, TypeVar, Generic, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, func
from sqlalchemy.orm import DeclarativeBase

ModelType = TypeVar("ModelType", bound=DeclarativeBase)


class BaseRepository(Generic[ModelType]):
    """
    通用 Repository 基类
    所有业务模块（Backend, Scrapy, Data Warehouse）的数据存取都应继承此类
    """

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    @property
    def _soft_delete_aware(self) -> bool:
        """模型是否带软删除列（hasattr 判断，无 Mixin 的表行为不变）"""
        return hasattr(self.model, "deleted_at")

    async def get_by_id(self, id: int) -> Optional[ModelType]:
        """根据 ID 获取单条记录（软删除表自动排除已删行）"""
        stmt = select(self.model).where(self.model.id == id)
        if self._soft_delete_aware:
            stmt = stmt.where(self.model.deleted_at.is_(None))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """获取列表（支持分页；软删除表自动排除已删行）"""
        stmt = select(self.model)
        if self._soft_delete_aware:
            stmt = stmt.where(self.model.deleted_at.is_(None))
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_all_with_deleted(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """管理视角：含已删除记录（回收站/审计用）"""
        stmt = select(self.model).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create(self, **kwargs) -> ModelType:
        """创建新记录"""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, id: int, **kwargs) -> Optional[ModelType]:
        """更新记录"""
        stmt = update(self.model).where(self.model.id == id).values(**kwargs)
        await self.session.execute(stmt)
        return await self.get_by_id(id)

    async def soft_delete(self, id: int) -> bool:
        """软删除：设置 deleted_at 而非物理删除（仅软删除表有效）"""
        if not self._soft_delete_aware:
            raise TypeError(f"{self.model.__name__} 无 SoftDeleteMixin，不支持 soft_delete（用 delete）")
        stmt = (
            update(self.model)
            .where(self.model.id == id, self.model.deleted_at.is_(None))
            .values(deleted_at=func.now())
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def restore(self, id: int) -> bool:
        """恢复软删除记录（deleted_at 置 NULL）"""
        if not self._soft_delete_aware:
            raise TypeError(f"{self.model.__name__} 无 SoftDeleteMixin，不支持 restore")
        stmt = (
            update(self.model)
            .where(self.model.id == id, self.model.deleted_at.isnot(None))
            .values(deleted_at=None)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def delete(self, id: int) -> bool:
        """物理删除（软删除表优先用 soft_delete；本方法保留给无 Mixin 表与确需硬删场景）"""
        stmt = delete(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def exists(self, **filters) -> bool:
        """检查记录是否存在（软删除表自动排除已删行）"""
        stmt = select(self.model).filter_by(**filters).limit(1)
        if self._soft_delete_aware:
            stmt = stmt.where(self.model.deleted_at.is_(None))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None
