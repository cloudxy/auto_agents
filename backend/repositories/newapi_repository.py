"""new-api 集成数据访问层 - 渠道事件与探针结果（阶段三）

两组 Repository 共存一文件（对应同一外部系统 new-api 的两类落库）：
- ChannelEventRepository：调度启停事件（写入 / 分页 / 按渠道 / 按动作过滤）
- ChannelProbeResultRepository：探针结果（写入 / 分页 / 按渠道 / 最近 verdict）

均基于 platform_core.repository.BaseRepository，只封装查询，不管理事务边界
（提交由调用方负责，与 ai_plan_repository 等既有风格一致）。
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.channel_event import ChannelEvent
from platform_core.models.channel_probe_result import ChannelProbeResult
from platform_core.repository import BaseRepository


class ChannelEventRepository(BaseRepository[ChannelEvent]):
    """channel_events 数据访问"""

    def __init__(self, session: AsyncSession):
        super().__init__(model=ChannelEvent, session=session)

    async def create_event(
        self,
        channel_id: int,
        action: str,
        usage: Optional[int] = None,
        limit_quota: Optional[int] = None,
        window_hours: Optional[int] = None,
        reason: Optional[str] = None,
        source: str = "scheduler",
    ) -> ChannelEvent:
        """写入一条渠道启停事件"""
        return await self.create(
            channel_id=channel_id,
            action=action,
            usage=usage,
            limit_quota=limit_quota,
            window_hours=window_hours,
            reason=reason,
            source=source,
        )

    async def list_events(
        self,
        skip: int = 0,
        limit: int = 20,
        channel_id: Optional[int] = None,
        action: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[ChannelEvent]:
        """分页查询事件（可按渠道/动作/来源过滤，时间倒序）"""
        stmt = select(ChannelEvent).order_by(ChannelEvent.id.desc()).offset(skip).limit(limit)
        if channel_id is not None:
            stmt = stmt.where(ChannelEvent.channel_id == channel_id)
        if action:
            stmt = stmt.where(ChannelEvent.action == action)
        if source:
            stmt = stmt.where(ChannelEvent.source == source)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_events(
        self,
        channel_id: Optional[int] = None,
        action: Optional[str] = None,
        source: Optional[str] = None,
    ) -> int:
        """事件总数（与 list_events 同过滤口径）"""
        stmt = select(func.count()).select_from(ChannelEvent)
        if channel_id is not None:
            stmt = stmt.where(ChannelEvent.channel_id == channel_id)
        if action:
            stmt = stmt.where(ChannelEvent.action == action)
        if source:
            stmt = stmt.where(ChannelEvent.source == source)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def count_events_since(self, since: datetime) -> int:
        """近窗口事件总数（created_at >= since，供健康页 24h 统计）"""
        stmt = select(func.count()).select_from(ChannelEvent).where(
            ChannelEvent.created_at >= since
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())


class ChannelProbeResultRepository(BaseRepository[ChannelProbeResult]):
    """channel_probe_results 数据访问"""

    def __init__(self, session: AsyncSession):
        super().__init__(model=ChannelProbeResult, session=session)

    async def create_result(
        self,
        channel_id: int,
        model: str,
        verdict: str,
        scores: Optional[dict] = None,
        latency_ms: Optional[int] = None,
        batch_id: str = "",
    ) -> ChannelProbeResult:
        """写入一条探针结果（batch_id 由调用方生成，同批多渠道共享）"""
        return await self.create(
            channel_id=channel_id,
            model=model,
            verdict=verdict,
            scores=scores,
            latency_ms=latency_ms,
            batch_id=batch_id,
        )

    async def list_results(
        self,
        skip: int = 0,
        limit: int = 20,
        channel_id: Optional[int] = None,
        verdict: Optional[str] = None,
        batch_id: Optional[str] = None,
    ) -> List[ChannelProbeResult]:
        """分页查询探针结果（可按渠道/判定/批次过滤，时间倒序）"""
        stmt = select(ChannelProbeResult).order_by(ChannelProbeResult.id.desc()).offset(skip).limit(limit)
        if channel_id is not None:
            stmt = stmt.where(ChannelProbeResult.channel_id == channel_id)
        if verdict:
            stmt = stmt.where(ChannelProbeResult.verdict == verdict)
        if batch_id:
            stmt = stmt.where(ChannelProbeResult.batch_id == batch_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_results(
        self,
        channel_id: Optional[int] = None,
        verdict: Optional[str] = None,
        batch_id: Optional[str] = None,
    ) -> int:
        """结果总数（与 list_results 同过滤口径）"""
        stmt = select(func.count()).select_from(ChannelProbeResult)
        if channel_id is not None:
            stmt = stmt.where(ChannelProbeResult.channel_id == channel_id)
        if verdict:
            stmt = stmt.where(ChannelProbeResult.verdict == verdict)
        if batch_id:
            stmt = stmt.where(ChannelProbeResult.batch_id == batch_id)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def latest_batch_id(self) -> Optional[str]:
        """最近一次探针批次 ID（时间倒序取首条；无探针记录时 None）"""
        stmt = select(ChannelProbeResult.batch_id).order_by(
            ChannelProbeResult.id.desc()
        ).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def count_results_by_verdict(self, batch_id: str) -> dict[str, int]:
        """指定批次的 verdict 分布（GROUP BY 一次聚合；供健康页概览）"""
        stmt = (
            select(ChannelProbeResult.verdict, func.count())
            .where(ChannelProbeResult.batch_id == batch_id)
            .group_by(ChannelProbeResult.verdict)
        )
        result = await self.session.execute(stmt)
        return {verdict: int(n) for verdict, n in result.all()}

    async def latest_verdict(self, channel_id: int) -> Optional[ChannelProbeResult]:
        """渠道最近一次探针结果（含 verdict，时间倒序取首条）"""
        stmt = (
            select(ChannelProbeResult)
            .where(ChannelProbeResult.channel_id == channel_id)
            .order_by(ChannelProbeResult.id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
