"""分发只从 pending 迁移（审计 BUG-12 回归）：重复 / 迟到的分发消息不得把终态任务翻回 running"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.tasks.consumer import SpiderTaskConsumer
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant


def _seed(db_session, status: str) -> int:
    async def _go():
        async with db_session() as s:
            t = Tenant(slug=f"cas-{status}", name="CAS")
            s.add(t)
            await s.flush()
            task = SpiderTask(spider_name="generic", tenant_id=t.id, status=status,
                              params=json.dumps({"urls": ["https://example.com/"]}))
            s.add(task)
            await s.flush()
            tid = int(task.id)
            await s.commit()
            return tid
    return asyncio.run(_go())


def _status(db_session, task_id: int) -> str:
    async def _go():
        async with db_session() as s:
            return (await s.get(SpiderTask, task_id)).status
    return asyncio.run(_go())


@pytest.mark.parametrize("terminal", ["completed", "failed"])
def test_duplicate_dispatch_does_not_revive_terminal_task(db_engine, db_session, terminal):
    task_id = _seed(db_session, terminal)
    consumer = SpiderTaskConsumer()
    consumer._redis = AsyncMock()
    consumer._redis.get = AsyncMock(return_value=None)
    msg = {"task_id": task_id, "spider_name": "generic",
           "params": json.dumps({"urls": ["https://example.com/"]})}

    async def _go():
        with patch("backend.tasks.consumer.SpiderTaskConsumer._engine", staticmethod(lambda: db_engine)):
            await consumer._dispatch(msg)

    asyncio.run(_go())
    assert _status(db_session, task_id) == terminal
    consumer._redis.rpush.assert_not_called()  # 未再投递 start URL（分发用 rpush）
    consumer._redis.sadd.assert_not_called()


def test_pending_task_dispatches(db_engine, db_session):
    task_id = _seed(db_session, "pending")
    consumer = SpiderTaskConsumer()
    consumer._redis = AsyncMock()
    consumer._redis.get = AsyncMock(return_value=None)
    msg = {"task_id": task_id, "spider_name": "generic",
           "params": json.dumps({"urls": ["https://example.com/"]})}

    async def _go():
        with patch("backend.tasks.consumer.SpiderTaskConsumer._engine", staticmethod(lambda: db_engine)):
            await consumer._dispatch(msg)

    asyncio.run(_go())
    assert _status(db_session, task_id) == "running"



def test_dispatch_uses_db_params_after_edit(db_engine, db_session):
    """审计 BUG-13：队列消息带旧 params，库内已被编辑——分发按库内 params 投递"""
    task_id = _seed(db_session, "pending")

    async def _edit():
        async with db_session() as s:
            row = await s.get(SpiderTask, task_id)
            row.params = json.dumps({"urls": ["https://edited.example/new"]})
            await s.commit()

    asyncio.run(_edit())
    consumer = SpiderTaskConsumer()
    consumer._redis = AsyncMock()
    consumer._redis.get = AsyncMock(return_value=None)
    stale = {"task_id": task_id, "spider_name": "generic",
             "params": json.dumps({"urls": ["https://example.com/"]})}

    async def _go():
        with patch("backend.tasks.consumer.SpiderTaskConsumer._engine", staticmethod(lambda: db_engine)):
            await consumer._dispatch(stale)

    asyncio.run(_go())
    pushed = " ".join(str(c.args) for c in consumer._redis.rpush.await_args_list)
    assert "edited.example" in pushed and "https://example.com/" not in pushed


def test_enqueue_and_edit_build_identical_queue_message():
    """投递与编辑搬迁共用唯一构造点：LREM 字节一致（原先编辑侧多带 tenant_id / priority 永不命中）"""
    from backend.services.spider_task_service import queue_message

    msg = queue_message(7, "generic", '{"urls": ["https://a"]}')
    assert json.loads(msg) == {"task_id": 7, "spider_name": "generic", "params": '{"urls": ["https://a"]}'}
