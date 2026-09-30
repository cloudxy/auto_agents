"""「暂停」先下线（决策 D6，2026-09-29「按照建议做」）

现有暂停只是让 Scrapy 丢弃后续请求：空闲 30 秒后任务被判为完成、请求丢失（审计 BUG-14）。
真挂起要等有客户需要再做；在那之前：
- 后端拒绝 pause（409 TASK_PAUSE_UNAVAILABLE），不写控制键
- resume 保留：只清掉旧版本留下的暂停键（幂等），让存量「暂停中」的任务能继续
- 终止照常
"""
from __future__ import annotations

import asyncio
import json

import pytest

from backend.services.spider_task_service import SpiderTaskService
from platform_core.exceptions import BusinessException
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant
from platform_core.queues import TASK_CONTROL_KEY
from stubs import FakeRedis


def _seed(db_session) -> int:
    async def _go():
        async with db_session() as s:
            t = Tenant(slug="d6-pause", name="暂停")
            s.add(t)
            await s.flush()
            task = SpiderTask(spider_name="generic", tenant_id=t.id, status="running",
                              params=json.dumps({"urls": ["https://example.com/"]}))
            s.add(task)
            await s.commit()
            return int(task.id)
    return asyncio.run(_go())


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("backend.services.spider_task_service.get_async_redis", lambda *a, **k: fake)
    return fake


def _control(db_session, task_id: int, action: str):
    async def _go():
        async with db_session() as s:
            return await SpiderTaskService(s).control_task(task_id, action)
    return asyncio.run(_go())


def test_pause_is_refused_and_writes_no_control_key(db_session, fake_redis):
    task_id = _seed(db_session)
    with pytest.raises(BusinessException) as exc:
        _control(db_session, task_id, "pause")
    assert exc.value.code == "TASK_PAUSE_UNAVAILABLE"
    assert exc.value.status_code == 409
    assert TASK_CONTROL_KEY.format(task_id=task_id) not in fake_redis.strings


def test_resume_clears_legacy_pause_key(db_session, fake_redis):
    task_id = _seed(db_session)
    key = TASK_CONTROL_KEY.format(task_id=task_id)
    fake_redis.strings[key] = "pause"
    out = _control(db_session, task_id, "resume")
    assert out["action"] == "resume"
    assert key not in fake_redis.strings
