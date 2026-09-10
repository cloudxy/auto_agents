"""操作审计日志数据访问层"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.operation_log import OperationLog
from platform_core.repository import BaseRepository


class OperationLogRepository(BaseRepository[OperationLog]):
    """审计日志 Repository（只增不改，支持分页查询）"""

    def __init__(self, session: AsyncSession):
        super().__init__(model=OperationLog, session=session)

    async def list_logs(
        self,
        skip: int = 0,
        limit: int = 20,
        action: Optional[str] = None,
        user: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[OperationLog]:
        """分页查询审计日志（最新优先，可按操作类型/操作人/时间范围过滤）"""
        stmt = select(OperationLog)
        if action:
            stmt = stmt.where(OperationLog.action == action)
        if user:
            stmt = stmt.where(OperationLog.actor_name == user)
        if start_time:
            stmt = stmt.where(OperationLog.created_at >= start_time)
        if end_time:
            stmt = stmt.where(OperationLog.created_at <= end_time)
        stmt = stmt.order_by(OperationLog.id.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_logs(
        self,
        action: Optional[str] = None,
        user: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """审计日志总数（与 list_logs 同过滤条件）"""
        stmt = select(func.count(OperationLog.id))
        if action:
            stmt = stmt.where(OperationLog.action == action)
        if user:
            stmt = stmt.where(OperationLog.actor_name == user)
        if start_time:
            stmt = stmt.where(OperationLog.created_at >= start_time)
        if end_time:
            stmt = stmt.where(OperationLog.created_at <= end_time)
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)
