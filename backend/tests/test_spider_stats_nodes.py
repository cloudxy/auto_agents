"""运行统计与 Worker 节点测试 - 运行统计聚合 + 节点列表心跳

约定：不连真实 MySQL/Redis，Repository/Redis 用 AsyncMock/MagicMock 桩。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.repositories.spider_task_repository import SpiderTaskRepository
from backend.services.spider_query_service import SpiderQueryService
from backend.services.spider_registry_service import SpiderRegistryService


def _query_service() -> SpiderQueryService:
    """查询域桩：stats 聚合"""
    svc = SpiderQueryService.__new__(SpiderQueryService)
    svc.session = MagicMock()
    svc.repo = MagicMock()
    svc.result_repo = MagicMock()
    return svc


def _registry_service() -> SpiderRegistryService:
    """注册表域桩：list_nodes（repo = 任务仓储，供活跃任务批查）"""
    svc = SpiderRegistryService.__new__(SpiderRegistryService)
    svc.session = MagicMock()
    svc.repo = MagicMock()
    return svc


# ---------------- 2.1 stats 聚合 ----------------
@pytest.mark.asyncio
async def test_stats_success_rate_and_fields():
    svc = _query_service()
    svc.repo.count_by_status = AsyncMock(
        return_value={"pending": 1, "running": 0, "completed": 3, "failed": 1}
    )
    svc.repo.avg_duration_seconds = AsyncMock(return_value=12.5)
    svc.repo.daily_task_counts = AsyncMock(return_value=[("2026-08-24", 2), ("2026-08-25", 2)])
    svc.repo.top_spiders_by_results = AsyncMock(return_value=[("example", 9)])
    svc.result_repo.daily_result_counts = AsyncMock(return_value=[("2026-08-25", 4)])

    stats = await svc.stats()

    assert stats.total_tasks == 5  # 1 pending + 0 running + 3 completed + 1 failed
    assert stats.success_rate == pytest.approx(0.75)  # 3/(3+1)
    assert stats.avg_duration_seconds == 12.5
    assert stats.total_results == 4
    assert [p.date for p in stats.daily_tasks] == ["2026-08-24", "2026-08-25"]
    assert stats.top_spiders[0].spider_name == "example"


@pytest.mark.asyncio
async def test_stats_no_finished_tasks_rate_none():
    svc = _query_service()
    svc.repo.count_by_status = AsyncMock(
        return_value={"pending": 2, "running": 1, "completed": 0, "failed": 0}
    )
    svc.repo.avg_duration_seconds = AsyncMock(return_value=None)
    svc.repo.daily_task_counts = AsyncMock(return_value=[])
    svc.repo.top_spiders_by_results = AsyncMock(return_value=[])
    svc.result_repo.daily_result_counts = AsyncMock(return_value=[])

    stats = await svc.stats()

    assert stats.success_rate is None  # 无终态任务时不产出成功率
    assert stats.avg_duration_seconds is None
    assert stats.daily_tasks == []


# ---------------- 2.2 list_nodes ----------------
@pytest.mark.asyncio
async def test_list_nodes_reads_heartbeat():
    svc = _registry_service()
    task = MagicMock()
    task.id = 17
    task.status = "running"
    # N+1 收口：活跃任务状态由 get_by_ids 一次批查回填
    svc.repo.get_by_ids = AsyncMock(return_value=[task])

    fake_redis = MagicMock()

    async def _scan_iter(match=None, count=None):
        yield "spider:worker:abc123"

    fake_redis.scan_iter = _scan_iter
    fake_redis.hgetall = AsyncMock(return_value={
        "pid": "4242",
        "spiders": "example,zhihu_feed",
        "started_at": "2026-08-25T12:00:00",
        "respawn_count": "3",
    })
    # 仅 example 有活跃任务（活跃键为 SET：smembers 返回成员集合）
    fake_redis.smembers = AsyncMock(
        side_effect=lambda key: {"17"} if "example" in key else set()
    )

    with patch("backend.services.spider_registry_service.get_async_redis", return_value=fake_redis):
        resp = await svc.list_nodes()

    assert resp.total == 1
    node = resp.items[0]
    assert node.worker_id == "abc123"
    assert node.pid == 4242
    assert node.spiders == ["example", "zhihu_feed"]
    assert node.respawn_count == 3
    assert node.online is True
    example_task = next(t for t in node.active_tasks if t.spider_name == "example")
    assert example_task.task_id == 17
    assert example_task.status == "running"
    zhihu_task = next(t for t in node.active_tasks if t.spider_name == "zhihu_feed")
    assert zhihu_task.task_id is None
    # 批查断言：一次 WHERE id IN（替代逐 task get_by_id 的 N+1）
    svc.repo.get_by_ids.assert_awaited_once_with([17])


@pytest.mark.asyncio
async def test_list_nodes_redis_down_returns_empty():
    svc = _registry_service()
    fake_redis = MagicMock()
    fake_redis.scan_iter.side_effect = ConnectionError("redis down")

    with patch("backend.services.spider_registry_service.get_async_redis", return_value=fake_redis):
        resp = await svc.list_nodes()

    assert resp.total == 0
    assert resp.items == []


# ---------------- Repository 层：get_by_ids 批查（N+1 消除） ----------------
class TestGetByIdsBatchQuery:
    """SpiderTaskRepository.get_by_ids：一次 WHERE id IN 替代逐条 get_by_id"""

    @staticmethod
    def _repo_with_rows(rows):
        session = MagicMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        session.execute = AsyncMock(return_value=result)
        return SpiderTaskRepository(session), session

    @pytest.mark.asyncio
    async def test_batch_query_uses_in_clause(self):
        rows = [MagicMock(id=17), MagicMock(id=23), MagicMock(id=42)]
        repo, session = self._repo_with_rows(rows)

        got = await repo.get_by_ids([17, 23, 42])

        assert got == rows
        session.execute.assert_awaited_once()
        # 语句含 IN 批查子句（非逐条等值查询）
        stmt = session.execute.await_args.args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "IN" in compiled

    @pytest.mark.asyncio
    async def test_empty_ids_short_circuits_without_db_hit(self):
        repo, session = self._repo_with_rows([])

        got = await repo.get_by_ids([])

        assert got == []
        session.execute.assert_not_awaited()
