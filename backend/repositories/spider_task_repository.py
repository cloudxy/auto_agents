"""爬虫任务数据访问层 - 封装所有 SpiderTask 相关的数据库操作"""
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import case, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.spider_task import SpiderTask
from platform_core.repository import BaseRepository


class SpiderTaskRepository(BaseRepository[SpiderTask]):
    """SpiderTask Repository —— 在 BaseRepository 之上扩展过滤/聚合"""

    def __init__(self, session: AsyncSession):
        super().__init__(model=SpiderTask, session=session)

    async def get_by_ids(self, ids: List[int]) -> List[SpiderTask]:
        """按 ID 列表批查任务（WHERE id IN），消除逐条 get_by_id 的 N+1"""
        if not ids:
            return []
        stmt = select(SpiderTask).where(SpiderTask.id.in_(ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_tasks(
        self,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> List[SpiderTask]:
        """分页查询任务，可按状态/优先级过滤（最新优先）"""
        stmt = select(SpiderTask)
        if status:
            stmt = stmt.where(SpiderTask.status == status)
        if priority:
            stmt = stmt.where(SpiderTask.priority == priority)
        stmt = stmt.order_by(SpiderTask.id.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, status: Optional[str] = None, priority: Optional[str] = None) -> int:
        """按状态/优先级计数（均为 None 为总数）"""
        stmt = select(func.count(SpiderTask.id))
        if status:
            stmt = stmt.where(SpiderTask.status == status)
        if priority:
            stmt = stmt.where(SpiderTask.priority == priority)
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

    async def avg_duration_seconds(self) -> Optional[float]:
        """已完成任务的平均运行时长（秒）：completed_at - started_at"""
        stmt = select(
            func.avg(func.timestampdiff(text("SECOND"), SpiderTask.started_at, SpiderTask.completed_at))
        ).where(
            SpiderTask.status == "completed",
            SpiderTask.started_at.isnot(None),
            SpiderTask.completed_at.isnot(None),
        )
        result = await self.session.execute(stmt)
        value = result.scalar()
        return float(value) if value is not None else None

    async def daily_task_counts(self, since: datetime) -> List[Tuple[str, int]]:
        """按日统计任务数（created_at >= since），返回 [(yyyy-mm-dd, count)] 升序"""
        day = func.date(SpiderTask.created_at)
        stmt = (
            select(day, func.count(SpiderTask.id))
            .where(SpiderTask.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
        result = await self.session.execute(stmt)
        return [(str(d), int(n)) for d, n in result.all()]

    async def recent_stats_by_spider(self, spider_name: str, limit: int = 10) -> dict:
        """查询某爬虫最近 N 次运行的统计：平均时长、成功率、平均结果数

        返回 {"avg_duration": float, "success_rate": float,
              "avg_result_count": float, "run_count": int}
        """
        # 子查询：取最近 N 条终态记录
        sub = (
            select(
                SpiderTask.status,
                SpiderTask.started_at,
                SpiderTask.completed_at,
                SpiderTask.result_count,
            )
            .where(
                SpiderTask.spider_name == spider_name,
                SpiderTask.status.in_(["completed", "failed"]),
            )
            .order_by(SpiderTask.created_at.desc())
            .limit(limit)
            .subquery()
        )
        stmt = select(
            func.avg(
                func.timestampdiff(text("SECOND"), sub.c.started_at, sub.c.completed_at)
            ).label("avg_duration"),
            func.sum(
                case((sub.c.status == "completed", 1), else_=0)
            ).label("completed_count"),
            func.count(sub.c.status).label("run_count"),
            func.avg(func.coalesce(sub.c.result_count, 0)).label("avg_result_count"),
        )
        result = await self.session.execute(stmt)
        row = result.one()
        run_count = int(row.run_count or 0)
        if run_count == 0:
            return {"avg_duration": 0.0, "success_rate": 0.0, "avg_result_count": 0.0, "run_count": 0}
        completed = int(row.completed_count or 0)
        return {
            "avg_duration": float(row.avg_duration or 0.0),
            "success_rate": round(completed / run_count, 4),
            "avg_result_count": float(row.avg_result_count or 0.0),
            "run_count": run_count,
        }

    async def top_spiders_by_results(self, limit: int = 5) -> List[Tuple[str, int]]:
        """各爬虫采集结果量 TopN（汇总任务表 result_count）"""
        stmt = (
            select(SpiderTask.spider_name, func.coalesce(func.sum(SpiderTask.result_count), 0))
            .group_by(SpiderTask.spider_name)
            .order_by(func.sum(SpiderTask.result_count).desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [(name, int(total)) for name, total in result.all()]

    async def count_by_spider(self, spider_name: str) -> int:
        """按爬虫名计数任务（删除定义前检查引用，非零拒绝）"""
        stmt = select(func.count(SpiderTask.id)).where(SpiderTask.spider_name == spider_name)
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def batch_increment_result_counts(self, counts: dict[int, int]) -> None:
        """批量原子累加 result_count（每条 task_id 一条 UPDATE 语句）

        用于消费者批量落库场景：一次 flush 可能包含多个 task 的多条结果，
        按 task_id 聚合后一次性 +N，避免逐条 commit。
        """
        for task_id, delta in counts.items():
            if delta > 0:
                await self.session.execute(
                    update(SpiderTask)
                    .where(SpiderTask.id == task_id)
                    .values(result_count=SpiderTask.result_count + delta)
                )
