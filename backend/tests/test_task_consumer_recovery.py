"""running 任务超时回收单测（P0-1b：孤儿任务置 failed，活跃任务不误杀）

约定：不连真实 Redis/DB——Redis 用 stubs.FakeRedis，DB 访问经 patch
替换 SpiderTaskRepository/AsyncSession；_fail_task 打桩观测调用。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import backend.tasks.consumer as consumer_mod
from backend.tasks.consumer import SpiderTaskConsumer
from platform_core.queues import ACTIVE_TASK_KEY
from stubs import FakeRedis, fake_settings


class _FakeTask:
    def __init__(self, task_id, spider_name):
        self.id = task_id
        self.spider_name = spider_name


class _FakeSessionCtx:
    """AsyncSession 上下文桩：进入返回空 session（回收路径只读不写）"""

    def __init__(self, engine):
        pass

    async def __aenter__(self):
        return MagicMock()

    async def __aexit__(self, *args):
        return False


def _consumer(redis: FakeRedis) -> SpiderTaskConsumer:
    svc = SpiderTaskConsumer()
    svc._redis = redis
    return svc


@pytest.mark.asyncio
async def test_recover_fails_orphans_and_spares_active():
    """活跃集合有记录的任务不回收；无记录（爬虫崩溃/回调丢失）者置 failed"""
    redis = FakeRedis()
    await redis.sadd(ACTIVE_TASK_KEY.format(spider_name="spider_a"), 1)  # task1 存活
    # task2(spider_b) 无活跃记录 → 孤儿；task3(spider_c) 同样孤儿
    svc = _consumer(redis)

    repo = MagicMock()
    repo.find_stale_running = AsyncMock(return_value=[
        _FakeTask(1, "spider_a"), _FakeTask(2, "spider_b"), _FakeTask(3, "spider_c"),
    ])
    fail = AsyncMock()
    with patch.object(consumer_mod, "settings", fake_settings(**{"TASKS.STALE_TASK_HOURS": 6})), \
         patch.object(consumer_mod, "SpiderTaskRepository", MagicMock(return_value=repo)), \
         patch.object(consumer_mod, "AsyncSession", _FakeSessionCtx), \
         patch.object(svc, "_fail_task", fail):
        await svc._recover_stale_once()

    assert fail.await_count == 2
    failed_ids = sorted(call.args[0] for call in fail.await_args_list)
    assert failed_ids == [2, 3]
    # 错误信息可操作（告诉用户为什么被回收、下一步做什么）
    assert "超时回收" in fail.await_args_list[0].args[1]


@pytest.mark.asyncio
async def test_recover_disabled_when_zero_hours():
    """STALE_TASK_HOURS=0：功能关闭，完全不触 DB"""
    svc = _consumer(FakeRedis())
    with patch.object(consumer_mod, "settings", fake_settings(**{"TASKS.STALE_TASK_HOURS": 0})), \
         patch.object(consumer_mod, "AsyncSession",
                      MagicMock(side_effect=AssertionError("关闭态不应查库"))):
        await svc._recover_stale_once()  # 直接返回，不抛


@pytest.mark.asyncio
async def test_recover_conservative_when_redis_error():
    """活跃集合查询失败：保守跳过（视为仍在运行），不误杀存活任务"""
    class _BrokenSetRedis(FakeRedis):
        async def sismember(self, key, member):
            raise RuntimeError("redis unstable")

    svc = _consumer(_BrokenSetRedis())
    repo = MagicMock()
    repo.find_stale_running = AsyncMock(return_value=[_FakeTask(9, "spider_x")])
    fail = AsyncMock()
    with patch.object(consumer_mod, "settings", fake_settings(**{"TASKS.STALE_TASK_HOURS": 6})), \
         patch.object(consumer_mod, "SpiderTaskRepository", MagicMock(return_value=repo)), \
         patch.object(consumer_mod, "AsyncSession", _FakeSessionCtx), \
         patch.object(svc, "_fail_task", fail):
        await svc._recover_stale_once()

    fail.assert_not_awaited()  # Redis 异常 → 不回收


# ---------------- P1-4：死信队列 ----------------
@pytest.mark.asyncio
async def test_accept_message_routes_missing_task_id_to_dead_letter():
    """缺 task_id 的结果消息转入 spider:item_dead 留档，不再静默丢弃"""
    import json as _json

    from platform_core.queues import DEAD_ITEM_QUEUE

    redis = FakeRedis()
    svc = _consumer(redis)
    raw = _json.dumps({"task_id": None, "spider_name": "generic", "item": {"url": "u"}})

    assert await svc._accept_message(raw, _json.loads(raw)) is False
    assert redis.lists[DEAD_ITEM_QUEUE] == [raw]

    # 正常消息直接放行，不动死信
    ok_raw = _json.dumps({"task_id": 5, "spider_name": "generic", "item": {}})
    assert await svc._accept_message(ok_raw, _json.loads(ok_raw)) is True
    assert len(redis.lists[DEAD_ITEM_QUEUE]) == 1


@pytest.mark.asyncio
async def test_dead_letter_write_failure_does_not_break_flow():
    """死信写入自身失败：不抛（回流主路径不受影响）"""
    import json as _json

    class _BrokenPushRedis(FakeRedis):
        async def rpush(self, key, *values):
            raise RuntimeError("redis full")

    svc = _consumer(_BrokenPushRedis())
    raw = _json.dumps({"task_id": None, "spider_name": "generic"})
    assert await svc._accept_message(raw, _json.loads(raw)) is False  # 不抛即通过


# ---------------- P1-4：积压 pending 对账重投 ----------------
class _FakePendingTask:
    def __init__(self, task_id, spider_name, params=None, priority="normal"):
        self.id = task_id
        self.spider_name = spider_name
        self.params = params or '{"urls": ["https://example.com"]}'
        self.priority = priority


@pytest.mark.asyncio
async def test_requeue_stale_pending_repushes_lost_messages():
    """dispatch 崩溃丢消息的 pending 任务：重建消息重新入优先级队列

    _MAX_REQUEUE_ATTEMPTS=2：连续两轮各重投一次（消息重建字段完整），
    计数内不置 failed；耗尽场景由下一个用例覆盖。
    """
    import json as _json

    from platform_core.queues import task_queue

    redis = FakeRedis()
    svc = _consumer(redis)
    repo = MagicMock()
    repo.find_stale_pending = AsyncMock(return_value=[_FakePendingTask(11, "generic")])
    fail = AsyncMock()
    with patch.object(consumer_mod, "settings", fake_settings(**{"TASKS.STALE_TASK_HOURS": 6})), \
         patch.object(consumer_mod, "SpiderTaskRepository", MagicMock(return_value=repo)), \
         patch.object(consumer_mod, "AsyncSession", _FakeSessionCtx), \
         patch.object(svc, "_fail_task", fail):
        await svc._requeue_stale_pending()
        await svc._requeue_stale_pending()

    queued = redis.lists[task_queue("normal")]
    assert len(queued) == 2  # 两轮各重投一次
    assert _json.loads(queued[0]) == {
        "task_id": 11,
        "spider_name": "generic",
        "params": '{"urls": ["https://example.com"]}',
        "priority": "normal",
    }
    fail.assert_not_awaited()  # 计数内不放弃


@pytest.mark.asyncio
async def test_requeue_gives_up_after_max_attempts():
    """重投次数耗尽仍无进展：置 failed 闭环（防每轮扫描无限重投）"""
    redis = FakeRedis()
    svc = _consumer(redis)
    svc._requeued_counts[12] = consumer_mod.SpiderTaskConsumer._MAX_REQUEUE_ATTEMPTS
    repo = MagicMock()
    repo.find_stale_pending = AsyncMock(return_value=[_FakePendingTask(12, "generic")])
    fail = AsyncMock()
    with patch.object(consumer_mod, "settings", fake_settings(**{"TASKS.STALE_TASK_HOURS": 6})), \
         patch.object(consumer_mod, "SpiderTaskRepository", MagicMock(return_value=repo)), \
         patch.object(consumer_mod, "AsyncSession", _FakeSessionCtx), \
         patch.object(svc, "_fail_task", fail):
        await svc._requeue_stale_pending()

    fail.assert_awaited_once()
    assert fail.await_args.args[0] == 12
