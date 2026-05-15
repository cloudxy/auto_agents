"""爬虫任务服务 - 业务逻辑编排层

职责：
- 调用 Repository 进行数据存取
- 处理业务规则（如：入队前校验、唯一性检查等）
- 返回可序列化的数据契约（Pydantic 或 dict）

约束（遵循 AuthService 范式）：
- 不直接写 SQL、不直接 session.execute
- 所有数据操作通过 Repository
"""
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.spider_task_repository import SpiderTaskRepository
from platform_core.logger import get_logger
from platform_core.schemas.spider import (
    SpiderStatsResponse,
    SpiderTaskListResponse,
    SpiderTaskResponse,
)

logger = get_logger("api")


class SpiderService:
    """爬虫任务编排"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = SpiderTaskRepository(session)

    async def list_tasks(
        self,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
    ) -> SpiderTaskListResponse:
        """分页列表（Service 层负责把 ORM 实体转成响应契约）"""
        items = await self.repo.list_tasks(skip=skip, limit=limit, status=status)
        total = await self.repo.count(status=status)
        return SpiderTaskListResponse(
            total=total,
            items=[SpiderTaskResponse.model_validate(t) for t in items],
        )

    async def enqueue(self, spider_name: str, params: Optional[str] = None) -> SpiderTaskResponse:
        """入队一个新任务（数据库登记 + 未来可投递到 Redis 队列）"""
        task = await self.repo.create(
            spider_name=spider_name,
            status="pending",
            params=params,
        )
        await self.session.commit()
        await self.session.refresh(task)
        logger.info(f"爬虫任务入队: spider={spider_name}, task_id={task.id}")
        # TODO: 后续在此处把 task_id 投递到 Redis 队列，由 scrapy consumer 消费
        return SpiderTaskResponse.model_validate(task)

    async def stats(self) -> SpiderStatsResponse:
        """供 /admin/stats 使用的聚合统计"""
        counts = await self.repo.count_by_status()
        total = sum(counts.values())
        return SpiderStatsResponse(
            total_tasks=total,
            pending=counts["pending"],
            running=counts["running"],
            completed=counts["completed"],
            failed=counts["failed"],
        )
