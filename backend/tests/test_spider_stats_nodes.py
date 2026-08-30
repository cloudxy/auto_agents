"""阶段 2 单测 - 2.1 运行统计聚合 + 2.2 Worker 节点列表

约定：与阶段 1 一致，不连真实 MySQL/Redis，Repository/Redis 用 AsyncMock/MagicMock 桩。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.spider_service import SpiderService


def _service() -> SpiderService:
    svc = SpiderService.__new__(SpiderService)
    svc.session = MagicMock()
    svc.repo = MagicMock()
    svc.result_repo = MagicMock()
    svc.notifier = MagicMock()
    return svc


# ---------------- 2.1 stats 聚合 ----------------
@pytest.mark.asyncio
async def test_stats_success_rate_and_fields():
    svc = _service()
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
    svc = _service()
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
    svc = _service()
    task = MagicMock()
    task.status = "running"
    svc.repo.get_by_id = AsyncMock(return_value=task)

    fake_redis = MagicMock()
    fake_redis.scan_iter.return_value = iter(["spider:worker:abc123"])
    fake_redis.hgetall.return_value = {
        "pid": "4242",
        "spiders": "example,zhihu_feed",
        "started_at": "2026-08-25T12:00:00",
        "respawn_count": "3",
    }
    # 仅 example 有活跃任务（活跃键为 SET：smembers 返回成员集合）
    fake_redis.smembers.side_effect = (
        lambda key: {"17"} if "example" in key else set()
    )

    with patch("backend.services.spider_service.redis_client", return_value=fake_redis):
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


@pytest.mark.asyncio
async def test_list_nodes_redis_down_returns_empty():
    svc = _service()
    fake_redis = MagicMock()
    fake_redis.scan_iter.side_effect = ConnectionError("redis down")

    with patch("backend.services.spider_service.redis_client", return_value=fake_redis):
        resp = await svc.list_nodes()

    assert resp.total == 0
    assert resp.items == []
