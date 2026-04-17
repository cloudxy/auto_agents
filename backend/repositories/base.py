"""数据访问层（Repository/DAO）- 统一管理数据库 CRUD 操作

设计原则：
- Repository 只负责数据存取，不包含业务逻辑
- Service 层调用 Repository，不直接写 SQL
- 所有查询方法返回 Pydantic Schema 或 ORM 模型
- 支持缓存策略（Redis）
"""
from typing import Optional, List, TypeVar, Generic, Type
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from backend.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """通用 Repository 基类
    
    提供基础 CRUD 操作，子类可扩展特定查询方法
    """
    
    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session
    
    async def get_by_id(self, id: int) -> Optional[ModelType]:
        """根据 ID 查询单条记录"""
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()
    
    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        order_by=None
    ) -> List[ModelType]:
        """查询所有记录（分页）"""
        query = select(self.model).offset(skip).limit(limit)
        
        if order_by:
            query = query.order_by(order_by)
        
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def count(self) -> int:
        """统计总记录数"""
        result = await self.session.execute(
            select(self.model).count()
        )
        return result.scalar_one()
    
    async def create(self, **kwargs) -> ModelType:
        """创建新记录"""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()  # 获取 ID
        await self.session.refresh(instance)
        return instance
    
    async def update(self, id: int, **kwargs) -> Optional[ModelType]:
        """更新记录"""
        instance = await self.get_by_id(id)
        if not instance:
            return None
        
        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        
        await self.session.flush()
        await self.session.refresh(instance)
        return instance
    
    async def delete(self, id: int) -> bool:
        """删除记录"""
        instance = await self.get_by_id(id)
        if not instance:
            return False
        
        await self.session.delete(instance)
        await self.session.flush()
        return True
    
    async def exists(self, **filters) -> bool:
        """检查记录是否存在"""
        query = select(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key):
                query = query.where(getattr(self.model, key) == value)
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None
