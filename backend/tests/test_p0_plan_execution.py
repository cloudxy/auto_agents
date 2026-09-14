"""P0 计划落地：API Key 哈希、配额旁路 hold 队列。"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.quota_service import QuotaExceededException
from platform_core.queues import item_hold_queue


def test_api_key_hash_is_sha256():
    from backend.services.api_key_service import _hash_key

    digest = _hash_key("ak_example")
    assert len(digest) == 64
    assert digest == _hash_key("ak_example")
    assert digest != _hash_key("ak_other")


@pytest.mark.asyncio
async def test_flush_quota_exceeded_parks_only_that_tenant():
    from backend.tasks.consumer import SpiderTaskConsumer

    consumer = SpiderTaskConsumer()
    consumer._redis = AsyncMock()
    messages = [
        {"task_id": 1, "spider_name": "s", "item": {"url": "u1", "title": "a", "content": "x"}},
        {"task_id": 2, "spider_name": "s", "item": {"url": "u2", "title": "b", "content": "y"}},
    ]
    t1 = MagicMock(params=None, tenant_id=9)
    t2 = MagicMock(params=None, tenant_id=8)
    repo = MagicMock()
    repo.get_by_id = AsyncMock(side_effect=lambda tid: {1: t1, 2: t2}[tid])
    repo.batch_increment_result_counts = AsyncMock()
    repo.find_by_content_hash = AsyncMock(return_value=None)
    session = AsyncMock()
    session.commit = AsyncMock()
    session.add_all = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    async def _quota(_self, tenant_id):
        if tenant_id == 9:
            raise QuotaExceededException("full")

    with patch("backend.tasks.consumer.AsyncSession", return_value=ctx), \
         patch("backend.tasks.consumer.SpiderTaskRepository", return_value=repo), \
         patch("backend.tasks.consumer.SpiderResultRepository", return_value=repo), \
         patch("backend.tasks.consumer.SpiderTaskConsumer._engine", staticmethod(lambda: object())), \
         patch("backend.services.quota_service.QuotaService.check_result_storage", _quota):
        await consumer._flush_batch(messages, {1: 1, 2: 1})

    consumer._redis.rpush.assert_awaited()
    assert consumer._redis.rpush.await_args.args[0] == item_hold_queue(9)
    session.add_all.assert_called()
    added = session.add_all.call_args.args[0]
    assert len(added) == 1
    assert added[0].tenant_id == 8


def test_bcrypt_rounds_honor_env(monkeypatch):
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")
    from backend.utils import auth as auth_mod

    assert auth_mod._bcrypt_rounds() == 4


def test_tenant_admin_cannot_write_platform_config(app, client, _reset_auth_override):
    """A2：租户 admin（非平台超管）不得改系统配置。"""
    from backend.app.api.deps import CurrentUser, get_current_user

    async def _tenant_admin():
        return CurrentUser(
            id=2, username="tenant-admin", role="admin",
            tenant_id=3, tenant_role="admin", is_platform_admin=False,
        )

    app.dependency_overrides[get_current_user] = _tenant_admin
    try:
        resp = client.put("/api/v1/configs/site.name", json={"value": "x"})
        assert resp.status_code in (401, 403, 404)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
