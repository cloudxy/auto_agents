"""AI 采集计划数据访问层 - 封装所有 AiPlan 相关的数据库操作（阶段二）"""
from typing import List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.ai_plan import AiPlan
from platform_core.repository import BaseRepository


class AiPlanRepository(BaseRepository[AiPlan]):
    """AiPlan Repository —— AI 采集计划状态机的 DB 数据源"""

    def __init__(self, session: AsyncSession):
        super().__init__(model=AiPlan, session=session)

    async def list_plans(
        self, skip: int = 0, limit: int = 20, status: Optional[str] = None
    ) -> List[AiPlan]:
        """分页查询计划（可按状态过滤，id 倒序：新计划优先）"""
        stmt = select(AiPlan).order_by(AiPlan.id.desc()).offset(skip).limit(limit)
        if status:
            stmt = stmt.where(AiPlan.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, status: Optional[str] = None) -> int:
        """计划总数（可按状态过滤）"""
        stmt = select(func.count()).select_from(AiPlan)
        if status:
            stmt = stmt.where(AiPlan.status == status)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def update_status(
        self,
        plan_id: int,
        status: str,
        error_message: Optional[str] = None,
        test_task_id: Optional[int] = None,
    ) -> Optional[AiPlan]:
        """状态机推进（error_message/test_task_id 一并落库，None 即清空）"""
        return await self.update(
            plan_id, status=status, error_message=error_message, test_task_id=test_task_id
        )

    async def claim_status(
        self,
        plan_id: int,
        to_status: str,
        blocked_statuses: tuple[str, ...],
        error_message: Optional[str] = None,
        test_task_id: Optional[int] = None,
    ) -> bool:
        """条件状态推进（M5 原子抢断）：单条 UPDATE 带状态守卫，rowcount 判定成败

        UPDATE ai_plans SET status=:to, ... WHERE id=:id AND status NOT IN (:blocked...)
        返回 False 表示计划不存在或当前状态处于占用集合（并发触发被拒），
        用数据库行级原子性替代 check-then-act，消除并发双跑窗口。
        """
        stmt = (
            update(AiPlan)
            .where(AiPlan.id == plan_id, AiPlan.status.not_in(list(blocked_statuses)))
            .values(status=to_status, error_message=error_message, test_task_id=test_task_id)
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        return bool(result.rowcount)
