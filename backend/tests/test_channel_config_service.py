"""渠道调度配置服务单测（4.2 接线：管理面 → Redis hash → 调度器）

约定：不连真实 Redis/new-api——redis 经 FakeRedis 注入 get_async_redis，
远程客户端经桩替换；事件落库经 patch 隔离（_main_async_session 独立事务）。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import backend.services.channel_config_service as cfg_mod
from backend.services.channel_config_service import ChannelConfigService
from backend.services.newapi_api import NEWAPI_CHANNEL_CFG_PREFIX
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.schemas.newapi import ChannelConfigInfo
from stubs import FakeRedis, fake_settings


def _client_stub(channels: list[dict], get_channel: dict | None = None) -> MagicMock:
    client = MagicMock()
    client.list_channels = AsyncMock(return_value=channels)
    client.get_channel = AsyncMock(return_value=get_channel)
    return client


def _service(redis: FakeRedis, client: MagicMock) -> ChannelConfigService:
    svc = ChannelConfigService()
    svc._client = client
    return svc


def _patch_redis(redis: FakeRedis):
    return patch.object(cfg_mod, "get_async_redis", lambda: redis)


def _patch_events():
    return patch.object(cfg_mod.ChannelConfigService, "_record_event", AsyncMock())


# ---------------- list_channels：配置合并视图 ----------------
@pytest.mark.asyncio
async def test_list_channels_merges_channel_and_global_config():
    redis = FakeRedis()
    # 渠道 1 有渠道级配置；渠道 2 无（走全局默认）；全局默认 = 0 时渠道 2 未纳管
    redis.hashes[f"{NEWAPI_CHANNEL_CFG_PREFIX}1"] = {
        "limit_quota": "500", "window_hours": "12", "cooldown_seconds": "1800",
    }
    client = _client_stub([
        {"id": 1, "name": "openai-main", "status": 1},
        {"id": 2, "name": "azure-bk", "status": 1},
    ])
    svc = _service(redis, client)

    with _patch_redis(redis), \
         patch.object(cfg_mod, "settings", fake_settings(**{
             "NEWAPI.DEFAULT_WINDOW_QUOTA": 0,
             "NEWAPI.DEFAULT_WINDOW_HOURS": 24,
             "NEWAPI.DEFAULT_COOLDOWN_SECONDS": 3600,
         })):
        rows = await svc.list_channels()

    by_id = {r.id: r for r in rows}
    assert by_id[1].effective_source == "channel"
    assert by_id[1].effective.limit_quota == 500
    assert by_id[1].effective.window_hours == 12
    assert by_id[1].config is not None

    # 全局默认 0：无渠道级配置 → 未纳管
    assert by_id[2].effective_source == "none"
    assert by_id[2].config is None


@pytest.mark.asyncio
async def test_list_channels_global_fallback_when_default_enabled():
    redis = FakeRedis()
    client = _client_stub([{"id": 7, "name": "ch7", "status": 1}])
    svc = _service(redis, client)
    with _patch_redis(redis), \
         patch.object(cfg_mod, "settings", fake_settings(**{
             "NEWAPI.DEFAULT_WINDOW_QUOTA": 300,
             "NEWAPI.DEFAULT_WINDOW_HOURS": 24,
             "NEWAPI.DEFAULT_COOLDOWN_SECONDS": 3600,
         })):
        rows = await svc.list_channels()
    assert rows[0].effective_source == "global"
    assert rows[0].effective.limit_quota == 300


@pytest.mark.asyncio
async def test_list_channels_unreachable_raises_business_error():
    client = MagicMock()
    client.list_channels = AsyncMock(side_effect=RuntimeError("conn refused"))
    svc = _service(FakeRedis(), client)
    with _patch_redis(FakeRedis()), pytest.raises(BusinessException) as exc:
        await svc.list_channels()
    assert exc.value.status_code == 502


# ---------------- set/clear：hash 契约 + 渠道存在性 ----------------
@pytest.mark.asyncio
async def test_set_config_writes_hash_fields_matching_scheduler_contract():
    redis = FakeRedis()
    client = _client_stub([], get_channel={"id": 3, "name": "ch3"})
    svc = _service(redis, client)
    info = ChannelConfigInfo(limit_quota=800, window_hours=6, cooldown_seconds=900)

    with _patch_redis(redis), _patch_events():
        result = await svc.set_config(3, info)

    assert result.limit_quota == 800
    fields = redis.hashes[f"{NEWAPI_CHANNEL_CFG_PREFIX}3"]
    # 字段名与 channel_scheduler_service._channel_cfg 读取契约一一对应
    assert fields["limit_quota"] == "800"
    assert fields["window_hours"] == "6"
    assert fields["cooldown_seconds"] == "900"


@pytest.mark.asyncio
async def test_set_config_rejects_missing_channel():
    client = _client_stub([], get_channel=None)  # 渠道不存在
    svc = _service(FakeRedis(), client)
    with _patch_redis(FakeRedis()), _patch_events():
        with pytest.raises(NotFoundException):
            await svc.set_config(999, ChannelConfigInfo(limit_quota=100))


@pytest.mark.asyncio
async def test_clear_config_deletes_hash_and_returns_previous():
    redis = FakeRedis()
    key = f"{NEWAPI_CHANNEL_CFG_PREFIX}5"
    redis.hashes[key] = {"limit_quota": "400", "window_hours": "24", "cooldown_seconds": "3600"}
    client = _client_stub([], get_channel={"id": 5, "name": "ch5"})
    svc = _service(redis, client)

    with _patch_redis(redis), _patch_events():
        previous = await svc.clear_config(5)

    assert previous is not None and previous.limit_quota == 400
    assert key not in redis.hashes  # hash 已清除（渠道退出渠道级纳管）

    # 无配置时清除：返回 None 不抛
    with _patch_redis(redis), _patch_events():
        assert await svc.clear_config(5) is None
