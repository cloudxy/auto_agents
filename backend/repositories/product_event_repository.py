"""产品事件仓储（追加写 + 超管按发生时间查）"""
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.product_event import ProductEvent
from platform_core.repository import BaseRepository


class ProductEventRepository(BaseRepository[ProductEvent]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=ProductEvent, session=session)

    async def list_by_occurred(
        self,
        *,
        event_name: Optional[str] = None,
        tenant_id: Optional[int] = None,
        occurred_from: Optional[datetime] = None,
        occurred_to: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[int, list[ProductEvent]]:
        stmt = select(ProductEvent)
        count_stmt = select(func.count()).select_from(ProductEvent)
        if event_name:
            stmt = stmt.where(ProductEvent.event_name == event_name)
            count_stmt = count_stmt.where(ProductEvent.event_name == event_name)
        if tenant_id is not None:
            stmt = stmt.where(ProductEvent.tenant_id == tenant_id)
            count_stmt = count_stmt.where(ProductEvent.tenant_id == tenant_id)
        if occurred_from is not None:
            stmt = stmt.where(ProductEvent.occurred_at >= occurred_from)
            count_stmt = count_stmt.where(ProductEvent.occurred_at >= occurred_from)
        if occurred_to is not None:
            stmt = stmt.where(ProductEvent.occurred_at <= occurred_to)
            count_stmt = count_stmt.where(ProductEvent.occurred_at <= occurred_to)
        total = int((await self.session.execute(count_stmt)).scalar_one() or 0)
        stmt = stmt.order_by(ProductEvent.occurred_at.desc()).offset(skip).limit(limit)
        rows = list((await self.session.execute(stmt)).scalars().all())
        return total, rows
