"""终止只影响本任务（审计 BUG-15 回归）

- 后端：待执行 / 运行中任务终止即置 cancelled（CAS），释放并发槽，写 stop 控制键；
  已结束任务不可终止；终止后迟到的 completed 回调不改写终态
- Scrapy：stop 只丢弃该任务的请求，不再 close_spider（原先关闭整个共享实例）
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.services.spider_task_service import SpiderTaskService
from platform_core.exceptions import BusinessException
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant
from platform_core.queues import ACTIVE_TASK_KEY, TASK_CONTROL_KEY
from stubs import FakeRedis


def _seed(db_session, status: str) -> tuple[int, int]:
    async def _go():
        async with db_session() as s:
            t = Tenant(slug=f"cancel-{status}", name="终止")
            s.add(t)
            await s.flush()
            task = SpiderTask(spider_name="generic", tenant_id=t.id, status=status,
                              params=json.dumps({"urls": ["https://example.com/"]}))
            s.add(task)
            await s.flush()
            ids = (int(task.id), int(t.id))
            await s.commit()
            return ids
    return asyncio.run(_go())


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("backend.services.spider_task_service.get_async_redis", lambda *a, **k: fake)
    return fake


@pytest.mark.parametrize("status", ["pending", "running"])
def test_stop_cancels_only_this_task(db_session, fake_redis, status):
    task_id, _tid = _seed(db_session, status)
    fake_redis.sets[ACTIVE_TASK_KEY.format(spider_name="generic")] = {str(task_id), "999"}

    async def _go():
        async with db_session() as s:
            out = await SpiderTaskService(s).control_task(task_id, "stop")
        async with db_session() as s:
            return out, (await s.get(SpiderTask, task_id)).status

    out, final = asyncio.run(_go())
    assert out["action"] == "stop" and final == "cancelled"
    assert fake_redis.strings.get(TASK_CONTROL_KEY.format(task_id=task_id)) == "stop"
    remaining = fake_redis.sets[ACTIVE_TASK_KEY.format(spider_name="generic")]
    assert str(task_id) not in {str(x) for x in remaining} and "999" in {str(x) for x in remaining}


def test_stop_finished_task_rejected(db_session, fake_redis):
    task_id, _ = _seed(db_session, "completed")

    async def _go():
        async with db_session() as s:
            await SpiderTaskService(s).control_task(task_id, "stop")

    with pytest.raises(BusinessException):
        asyncio.run(_go())


def test_late_completed_callback_keeps_cancelled(db_session, fake_redis):
    task_id, _ = _seed(db_session, "running")

    async def _go():
        async with db_session() as s:
            await SpiderTaskService(s).control_task(task_id, "stop")
        async with db_session() as s:
            await SpiderTaskService(s).finish_task(task_id, "completed")
        async with db_session() as s:
            return (await s.get(SpiderTask, task_id)).status

    assert asyncio.run(_go()) == "cancelled"


def test_scrapy_stop_drops_requests_without_closing_spider():
    scrapy_dir = str(Path(__file__).resolve().parents[2] / "scrapy")
    if scrapy_dir not in sys.path:
        sys.path.insert(0, scrapy_dir)
    os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "settings")
    mw_mod = importlib.import_module("middlewares")
    ignore = importlib.import_module("scrapy.exceptions").IgnoreRequest
    req = importlib.import_module("scrapy.http").Request("https://example.com/", meta={"task_id": 5})
    # 非空即视为「已配置」（未配置时中间件整体停用）；客户端下面直接注入，不会真连
    mw = mw_mod.TaskControlMiddleware(redis_url="configured-placeholder")
    client = MagicMock()
    client.get.return_value = "stop"
    mw._client = client
    spider = MagicMock()
    with pytest.raises(ignore):
        mw.process_request(req, spider)
    spider.crawler.engine.close_spider.assert_not_called()
