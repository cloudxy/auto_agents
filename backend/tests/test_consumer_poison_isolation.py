"""回流毒消息隔离（审计 R2-1 / BUG-05 / P0-4 回归）

真库（SQLite 独立文件库）驱动 _flush_batch，锁定：
- 唯一键 (tenant_id, spider_name, content_hash) 对非增量任务同样生效：批内重复 /
  库内已存在不再让整批 IntegrityError，好数据照常落库，result_count 只计新增
- 批次数据类失败 → 逐条隔离；单条连续失败达上限进死信，不再无限回 REDO
- 基础设施类失败 → 整批暂存 REDO，不计重放次数
- 多存储镜像在 commit 之后：提交失败不产生镜像
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError

from backend.tasks.consumer import _MAX_REDO_ATTEMPTS, SpiderTaskConsumer
from platform_core.models.spider_result import SpiderResult
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant
from platform_core.queues import DEAD_ITEM_QUEUE, ITEM_REDO_QUEUE


def _seed_task(db_session, *, params: str = "{}") -> tuple[int, int]:
    async def _go():
        async with db_session() as s:
            t = Tenant(slug="poison-co", name="毒消息公司")
            s.add(t)
            await s.flush()
            task = SpiderTask(spider_name="flow_generic", tenant_id=t.id, status="running",
                              params=params)
            s.add(task)
            await s.flush()
            ids = (int(task.id), int(t.id))
            await s.commit()
            return ids

    return asyncio.run(_go())


def _msg(task_id: int, url: str, title: str = "t") -> dict:
    return {"task_id": task_id, "spider_name": "flow_generic",
            "item": {"url": url, "title": title, "content": "c"}}


def _consumer() -> SpiderTaskConsumer:
    c = SpiderTaskConsumer()
    c._redis = AsyncMock()
    c._fail_task = AsyncMock()
    return c


def _results(db_session) -> tuple[int, int]:
    async def _go():
        async with db_session() as s:
            n = (await s.execute(select(func.count(SpiderResult.id)))).scalar_one()
            rc = (await s.execute(select(SpiderTask.result_count))).scalar_one()
            return int(n), int(rc or 0)

    return asyncio.run(_go())


def _run_flush(consumer, db_engine, messages):
    async def _go():
        with patch("backend.tasks.consumer.SpiderTaskConsumer._engine",
                   staticmethod(lambda: db_engine)):
            await consumer._flush_batch(messages, {})

    asyncio.run(_go())


def test_duplicates_in_batch_do_not_poison_non_incremental_task(db_engine, db_session):
    task_id, _tid = _seed_task(db_session)
    consumer = _consumer()
    batch = [_msg(task_id, "https://a/1"), _msg(task_id, "https://a/1"), _msg(task_id, "https://a/2")]
    _run_flush(consumer, db_engine, batch)
    assert _results(db_session) == (2, 2)


def test_existing_rows_skipped_and_new_rows_land(db_engine, db_session):
    task_id, _tid = _seed_task(db_session)
    consumer = _consumer()
    _run_flush(consumer, db_engine, [_msg(task_id, "https://a/1")])
    # 重放同一条 + 一条新数据：原先整批 IntegrityError → REDO 无限循环，新数据永远落不了库
    _run_flush(consumer, db_engine, [_msg(task_id, "https://a/1"), _msg(task_id, "https://a/3")])
    assert _results(db_session) == (2, 2)


def test_data_error_isolates_poison_and_lands_good_items():
    consumer = _consumer()
    good, poison = {"task_id": 1, "k": "good"}, {"task_id": 1, "k": "poison"}
    flushed: list[dict] = []

    async def fake_flush(messages, _counts):
        if messages[0]["k"] == "poison":
            raise IntegrityError("insert", {}, Exception("dup"))
        flushed.extend(messages)

    consumer._flush_batch = fake_flush
    consumer._park_messages = AsyncMock()
    asyncio.run(consumer._recover_failed_batch(
        [good, poison], IntegrityError("insert", {}, Exception("dup"))))

    assert flushed == [good]
    queue, parked = consumer._park_messages.await_args.args
    assert queue == ITEM_REDO_QUEUE
    assert parked[0]["k"] == "poison" and parked[0]["_redo_attempts"] == 1


def test_poison_goes_dead_letter_after_max_attempts():
    consumer = _consumer()
    poison = {"task_id": 1, "k": "poison", "_redo_attempts": _MAX_REDO_ATTEMPTS - 1}

    async def fake_flush(_messages, _counts):
        raise ValueError("bad row")

    consumer._flush_batch = fake_flush
    consumer._park_messages = AsyncMock()
    asyncio.run(consumer._recover_failed_batch([poison], ValueError("bad row")))

    queue, parked = consumer._park_messages.await_args.args
    assert queue == DEAD_ITEM_QUEUE
    assert parked[0]["_redo_attempts"] == _MAX_REDO_ATTEMPTS
    assert "连续失败" in parked[0]["_reject_reason"]


def test_transient_error_parks_whole_batch_without_attempts():
    consumer = _consumer()
    consumer._flush_batch = AsyncMock()
    consumer._park_messages = AsyncMock()
    batch = [{"task_id": 1}, {"task_id": 2}]
    asyncio.run(consumer._recover_failed_batch(
        batch, OperationalError("select", {}, Exception("gone away"))))

    consumer._flush_batch.assert_not_awaited()  # 库不可用时不做逐条重试
    queue, parked = consumer._park_messages.await_args.args
    assert queue == ITEM_REDO_QUEUE and parked == batch
    assert all("_redo_attempts" not in m for m in parked)


def test_mirror_happens_only_after_commit(db_engine, db_session):
    task_id, _tid = _seed_task(db_session, params=json.dumps({"store_to": ["redis"]}))
    consumer = _consumer()
    consumer._mirror_batch = AsyncMock()

    async def _go():
        with patch("backend.tasks.consumer.SpiderTaskConsumer._engine",
                   staticmethod(lambda: db_engine)), \
             patch("sqlalchemy.ext.asyncio.AsyncSession.commit",
                   AsyncMock(side_effect=OperationalError("commit", {}, Exception("lost")))):
            await consumer._flush_batch([_msg(task_id, "https://m/1")], {})

    with pytest.raises(OperationalError):
        asyncio.run(_go())
    consumer._mirror_batch.assert_not_awaited()
