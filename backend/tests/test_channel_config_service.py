"""渠道调度配置服务单测（T-18：网关模型 + Redis expand）"""
from unittest.mock import AsyncMock, patch

import pytest

import backend.services.channel_config_service as cfg_mod
from backend.services.channel_config_service import ChannelConfigService
from backend.services.newapi_api import NEWAPI_CHANNEL_CFG_PREFIX, RELAY_CHANNEL_CFG_PREFIX
from platform_core.exceptions import NotFoundException
from platform_core.schemas.newapi import ChannelConfigInfo
from stubs import FakeRedis, fake_settings


def _service() -> ChannelConfigService:
    return ChannelConfigService()


def _patch_redis(redis: FakeRedis):
    return patch.object(cfg_mod, "get_async_redis", lambda: redis)


def _patch_events():
    return patch.object(cfg_mod.ChannelConfigService, "_record_event", AsyncMock())


def _patch_models(models=None, error=None):
    async def _list():
        if error is not None:
            raise error
        return {"data": models if models is not None else []}

    return patch.object(cfg_mod.gw_admin, "list_models", _list)


_MODEL_1 = {
    "model_name": "openai-main",
    "model_info": {"id": "1"},
    "litellm_params": {},
}
_MODEL_2 = {
    "model_name": "azure-bk",
    "model_info": {"id": "2"},
    "litellm_params": {},
}


@pytest.mark.asyncio
async def test_list_channels_merges_channel_and_global_config():
    redis = FakeRedis()
    redis.hashes[f"{RELAY_CHANNEL_CFG_PREFIX}1"] = {
        "limit_quota": "500", "window_hours": "12", "cooldown_seconds": "1800",
    }
    svc = _service()
    with _patch_redis(redis), \
         _patch_models([_MODEL_1, _MODEL_2]), \
         patch.object(cfg_mod, "settings", fake_settings(**{
             "RELAY.DEFAULT_WINDOW_QUOTA": 0,
             "RELAY.DEFAULT_WINDOW_HOURS": 24,
             "RELAY.DEFAULT_COOLDOWN_SECONDS": 3600,
         })):
        rows = await svc.list_channels()

    by_ref = {r.gateway_ref: r for r in rows}
    assert by_ref["1"].effective_source == "channel"
    assert by_ref["1"].effective.limit_quota == 500
    assert by_ref["1"].config is not None
    assert by_ref["2"].effective_source == "none"
    assert by_ref["2"].config is None


@pytest.mark.asyncio
async def test_list_channels_global_fallback_when_default_enabled():
    redis = FakeRedis()
    svc = _service()
    with _patch_redis(redis), \
         _patch_models([{"model_name": "ch7", "model_info": {"id": "7"}}]), \
         patch.object(cfg_mod, "settings", fake_settings(**{
             "RELAY.DEFAULT_WINDOW_QUOTA": 300,
             "RELAY.DEFAULT_WINDOW_HOURS": 24,
             "RELAY.DEFAULT_COOLDOWN_SECONDS": 3600,
         })):
        rows = await svc.list_channels()
    assert rows[0].effective_source == "global"
    assert rows[0].effective.limit_quota == 300


@pytest.mark.asyncio
async def test_list_channels_unreachable_returns_empty():
    svc = _service()
    with _patch_redis(FakeRedis()), _patch_models(error=RuntimeError("conn refused")):
        rows = await svc.list_channels()
    assert rows == []


@pytest.mark.asyncio
async def test_set_config_writes_relay_hash():
    redis = FakeRedis()
    svc = _service()
    info = ChannelConfigInfo(limit_quota=800, window_hours=6, cooldown_seconds=900)
    with _patch_redis(redis), _patch_events(), _patch_models([
        {"model_name": "ch3", "model_info": {"id": "3"}},
    ]):
        result = await svc.set_config(3, info)

    assert result.limit_quota == 800
    fields = redis.hashes[f"{RELAY_CHANNEL_CFG_PREFIX}3"]
    assert fields["limit_quota"] == "800"
    assert fields["window_hours"] == "6"
    assert fields["cooldown_seconds"] == "900"
    assert f"{NEWAPI_CHANNEL_CFG_PREFIX}3" not in redis.hashes


@pytest.mark.asyncio
async def test_set_config_rejects_missing_channel():
    svc = _service()
    with _patch_redis(FakeRedis()), _patch_events(), _patch_models([]):
        with pytest.raises(NotFoundException):
            await svc.set_config(999, ChannelConfigInfo(limit_quota=100))


@pytest.mark.asyncio
async def test_clear_config_deletes_hash_and_returns_previous():
    redis = FakeRedis()
    key = f"{RELAY_CHANNEL_CFG_PREFIX}5"
    redis.hashes[key] = {"limit_quota": "400", "window_hours": "24", "cooldown_seconds": "3600"}
    svc = _service()

    with _patch_redis(redis), _patch_events():
        previous = await svc.clear_config(5)

    assert previous is not None and previous.limit_quota == 400
    assert key not in redis.hashes

    with _patch_redis(redis), _patch_events():
        assert await svc.clear_config(5) is None


@pytest.mark.asyncio
async def test_dual_read_prefers_old_key():
    redis = FakeRedis()
    redis.hashes[f"{NEWAPI_CHANNEL_CFG_PREFIX}1"] = {
        "limit_quota": "11", "window_hours": "2", "cooldown_seconds": "60",
    }
    svc = _service()
    with _patch_redis(redis):
        cfg = await svc._read_cfg(channel_id=1, gateway_ref="1")
    assert cfg is not None
    assert cfg.limit_quota == 11


@pytest.mark.asyncio
async def test_spoofed_probe_does_not_rewrite_relay_cfg():
    """GWT-07.6：伪装判定不得改 relay 窗口/额度。"""
    from unittest.mock import AsyncMock, patch

    from backend.services import channel_probe_service as probe_mod
    from backend.services.channel_probe_service import (
        DEFAULT_PROBE_QUESTIONS,
        ChannelProbeService,
    )

    redis = FakeRedis()
    key = f"{RELAY_CHANNEL_CFG_PREFIX}2"
    redis.hashes[key] = {
        "limit_quota": "500", "window_hours": "12", "cooldown_seconds": "1800",
    }
    snapshot = dict(redis.hashes[key])
    svc = ChannelProbeService.__new__(ChannelProbeService)
    svc._running = False
    svc._loop_task = None
    svc._redis = redis
    svc._record_probe_result = AsyncMock()

    async def _spoof(body, **kwargs):
        return {
            "choices": [{"message": {"content": "我是 GLM-4"}}],
            "usage": {"total_tokens": 20},
            "model": body.get("model"),
        }

    with patch.object(probe_mod, "chat_completions", _spoof), \
         patch.object(probe_mod, "NotifyService") as notify_cls:
        notify_cls.return_value.notify_text = AsyncMock()
        await svc._probe_channel(
            {"gateway_ref": "2", "model_name": "gpt-4o", "name": "gpt-4o"},
            None, DEFAULT_PROBE_QUESTIONS, "b",
        )
    assert redis.hashes[key] == snapshot
    assert f"{RELAY_CHANNEL_CFG_PREFIX}2" in redis.hashes


@pytest.mark.asyncio
async def test_manual_disabled_on_old_cfg_key_blocks_recovery():
    """expand 双读：旧 newapi:channel:cfg:{id} 的人工禁用仍挡住冷却恢复。"""
    import json
    import time
    from unittest.mock import AsyncMock, patch

    from backend.services import channel_scheduler_service as sched_mod
    from backend.services.channel_scheduler_service import ChannelSchedulerService
    from backend.services.newapi_api import RELAY_CHANNEL_STATE_PREFIX

    redis = FakeRedis()
    redis.hashes[f"{NEWAPI_CHANNEL_CFG_PREFIX}7"] = {
        "limit_quota": "100", "window_hours": "24", "cooldown_seconds": "3600",
        "manual_disabled": "1",
    }
    redis.strings[f"{RELAY_CHANNEL_STATE_PREFIX}7"] = json.dumps({
        "cooldown_until": int(time.time()) - 5, "last_usage": 9,
    })
    writes: list = []

    async def _cap(body, **_k):
        writes.append(body)
        return {}

    svc = ChannelSchedulerService.__new__(ChannelSchedulerService)
    svc._running = False
    svc._loop_task = None
    svc._redis = redis
    svc._record_event = AsyncMock()
    with patch.object(sched_mod, "settings", fake_settings(**{
            "RELAY.DEFAULT_WINDOW_QUOTA": 0})), \
         patch.object(sched_mod.gw_admin, "list_models", AsyncMock(return_value={
             "data": [{"model_name": "m7", "model_info": {"id": "7"}}],
         })), \
         patch.object(sched_mod.gw_admin, "get_spend_logs", AsyncMock(return_value=[])), \
         patch.object(sched_mod.gw_admin, "create_budget", _cap), \
         patch.object(sched_mod.gw_admin, "update_budget", _cap):
        await svc._tick_once()
    assert writes == []
    assert f"{RELAY_CHANNEL_STATE_PREFIX}7" not in redis.strings
