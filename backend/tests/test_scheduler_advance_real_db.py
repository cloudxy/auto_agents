"""调度推进真库回归（审计 B3-1 / BUG-06 / P0-5）

原缺陷：入队 commit 使同会话内所有计划实例过期，随后读 schedule.id / cron_expr
触发异步惰性加载（MissingGreenlet）被吞掉 → next_run_at 永不推进；同轮后续计划
在 _fire 入口即抛错，整轮失败。既有用例全部 MagicMock，无法暴露该缺陷。
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select

from backend.services.schedule_service import SpiderScheduler
from platform_core.exceptions import BusinessException
from platform_core.models.spider_schedule import SpiderSchedule
from platform_core.models.tenant import Tenant
from platform_core.timeutil import utcnow


class _HealthyLock:
    lost = False


@asynccontextmanager
async def _fake_lock(redis, key, ttl, **kwargs):
    yield _HealthyLock()


def _seed(db_session, n: int) -> list[int]:
    async def _go():
        async with db_session() as s:
            t = Tenant(slug="sched-co", name="调度公司")
            s.add(t)
            await s.flush()
            rows = [
                SpiderSchedule(spider_name=f"sched-{i}", cron_expr="*/5 * * * *", params=None,
                               enabled=True, tenant_id=t.id,
                               next_run_at=utcnow() - timedelta(minutes=10))
                for i in range(n)
            ]
            s.add_all(rows)
            await s.flush()
            ids = [int(r.id) for r in rows]
            await s.commit()
            return ids

    return asyncio.run(_go())


def _rows(db_session):
    async def _go():
        async with db_session() as s:
            return list((await s.execute(select(SpiderSchedule).order_by(SpiderSchedule.id))).scalars())

    return asyncio.run(_go())


def _run_tick(db_engine, enqueue_side_effect):
    """SpiderService 桩：enqueue 像真实实现一样 commit 调用方会话（这是缺陷触发点）"""
    calls: list[str] = []

    class _CommittingService:
        def __init__(self, session):
            self.session = session

        async def enqueue(self, *, spider_name, **_kw):
            calls.append(spider_name)
            await self.session.commit()
            if enqueue_side_effect is not None:
                raise enqueue_side_effect

    scheduler = SpiderScheduler()
    settings_mock = MagicMock()
    settings_mock.get = lambda key, default=None: 30 if key == "SCHEDULER.TICK_SECONDS" else default

    async def _go():
        with patch("backend.services.schedule_service.distributed_lock", _fake_lock), \
             patch.object(SpiderScheduler, "_engine", return_value=db_engine), \
             patch("backend.services.schedule_service.settings", settings_mock), \
             patch("backend.services.schedule_service.SpiderService", _CommittingService), \
             patch("backend.services.schedule_service.AlertService") as alert_cls:
            alert_cls.return_value.evaluate_queue_depth = AsyncMock(return_value=0)
            await scheduler._tick_once()

    asyncio.run(_go())
    return calls


def test_tick_advances_every_due_schedule_after_enqueue_commit(db_engine, db_session):
    _seed(db_session, 2)
    before = utcnow()
    calls = _run_tick(db_engine, None)
    assert sorted(calls) == ["sched-0", "sched-1"]  # 两条都触发（原先第二条在入口即抛错）
    for row in _rows(db_session):
        assert row.last_run_at is not None
        assert row.next_run_at.replace(tzinfo=None) > before  # 已推进到未来


def test_tick_advances_even_when_enqueue_rejected(db_engine, db_session):
    _seed(db_session, 2)
    before = utcnow()
    calls = _run_tick(db_engine, BusinessException("已有进行中的任务"))
    assert len(calls) == 2
    for row in _rows(db_session):
        assert row.next_run_at.replace(tzinfo=None) > before
