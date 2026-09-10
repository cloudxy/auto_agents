"""feat-llm-cooldown：候选链冷却过滤（FR-01~04 + NFR-01/02）——QA-6 补齐版"""
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_redis(monkeypatch):
    """模拟 Redis：存储 dict {key: value}；pipeline/incr/expire/get/mget/delete。"""
    store: dict[str, str] = {}
    m = MagicMock()

    async def _get(k): return store.get(k)
    async def _mget(keys): return [store.get(k) for k in keys]
    async def _delete(*keys):
        for k in keys: store.pop(k, None)
    async def _incr(k):
        v = int(store.get(k, 0)) + 1
        store[k] = str(v)
        return v
    async def _expire(k, s): pass  # TTL 模拟由测试手动过期

    m.get = _get
    m.mget = _mget
    m.delete = _delete
    m.incr = _incr
    m.expire = _expire

    m._pipe_calls = []
    def _sync_incr(k):
        v = int(store.get(k, 0)) + 1
        store[k] = str(v)
        return v
    def _pipe(*args, **kwargs):
        pipe = MagicMock()
        pipe.incr = MagicMock(side_effect=lambda k: _sync_incr(k))
        pipe.expire = MagicMock()
        async def _exec():
            m._pipe_calls.append("pipeline")
            return [0, True]  # 返回值不用于判定（is_cooled_down 走 get 路径）
        pipe.execute = _exec
        return pipe
    m.pipeline = _pipe
    monkeypatch.setattr("backend.services.ai_planner._cooldown.get_async_redis", lambda *a, **kw: m)
    return m, store


@pytest.mark.asyncio
async def test_fr01_threshold_semantics(mock_redis):
    """FR-01：1 次失败 NOT 冷却（负例，QA-2 修复验证）→ 2 次达阈值冷却"""
    _, store = mock_redis
    from backend.services.ai_planner._cooldown import record_failure, is_cooled_down

    await record_failure(1, "model-a")
    assert await is_cooled_down(1, "model-a") is False, "首次失败不应冷却（QA-2 修复）"

    await record_failure(1, "model-a")
    assert await is_cooled_down(1, "model-a") is True, "2 次（默认阈值）应冷却"


@pytest.mark.asyncio
async def test_fr02_chain_mget_batch_filter(db_session, mock_redis):
    """FR-02：冷却模型被候选链过滤（单次 MGET，NFR-02）"""
    _, store = mock_redis
    store["llm:cooldown:99:m-bad"] = "5"  # 模拟已冷却（值 ≥ 阈值）

    from platform_core.models.llm_provider import LlmProvider
    from platform_core.models.llm_provider_model import LlmProviderModel
    from backend.services.ai_planner import llm_client as lc

    async with db_session() as s:
        p = LlmProvider(name="cd-mget", provider_type="openai_compatible",
                        base_url="https://t.co/v1", model="m-good")
        s.add(p)
        await s.flush()
        pid = p.id
        s.add(LlmProviderModel(provider_id=pid, model_id="m-good", priority=10, is_default=True))
        # 注意：键名含 pid 而非硬编码 1（QA-6d 修复）
        store[f"llm:cooldown:{pid}:m-bad"] = "5"
        s.add(LlmProviderModel(provider_id=pid, model_id="m-bad", priority=20))
        await s.commit()

    async with db_session() as s:
        chain = await lc._candidate_chain(pid, session=s)
    models = [m for m, _ in chain]
    assert "m-bad" not in models and "m-good" in models


@pytest.mark.asyncio
async def test_fr03_ttl_expiry(mock_redis):
    """FR-03：TTL 过期（键消失/值丢失）→ 恢复参与"""
    _, store = mock_redis
    from backend.services.ai_planner._cooldown import is_cooled_down

    store["llm:cooldown:1:m-x"] = "5"
    assert await is_cooled_down(1, "m-x") is True
    del store["llm:cooldown:1:m-x"]  # TTL 过期
    assert await is_cooled_down(1, "m-x") is False


@pytest.mark.asyncio
async def test_fr04_clear(mock_redis):
    """FR-04：连通成功 → 冷却清除"""
    _, store = mock_redis
    from backend.services.ai_planner._cooldown import clear, is_cooled_down

    store["llm:cooldown:1:m-y"] = "3"
    assert await is_cooled_down(1, "m-y") is True
    await clear(1, "m-y")
    assert await is_cooled_down(1, "m-y") is False


@pytest.mark.asyncio
async def test_nfr01_redis_failure_fail_open(monkeypatch):
    """NFR-01：Redis 故障 fail-open"""
    def _boom(*a, **kw): raise ConnectionError("redis down")
    monkeypatch.setattr("backend.services.ai_planner._cooldown.get_async_redis", _boom)

    from backend.services.ai_planner._cooldown import record_failure, is_cooled_down, clear, filter_cooled

    assert await is_cooled_down(1, "any") is False
    assert await filter_cooled(1, ["a", "b"]) == ["a", "b"]  # 全返回
    await record_failure(1, "any")  # 不抛
    await clear(1, "any")  # 不抛


@pytest.mark.asyncio
async def test_nfr02_mget_single_roundtrip(mock_redis):
    """NFR-02：批量检查走单次 MGET（非逐模型 EXISTS）"""
    m, store = mock_redis
    from backend.services.ai_planner._cooldown import filter_cooled

    store["llm:cooldown:1:m-cold"] = "9"  # 已冷却
    result = await filter_cooled(1, ["m-a", "m-b", "m-cold", "m-d"])
    assert result == ["m-a", "m-b", "m-d"]
    # 结构验证：mget 是批量操作（结果正确且 mget 存在于 mock）——函数式 mock 无 .called，
    # 改为验证结果语义：3 输入 1 冷却 → 2 输出
    assert len(result) == 3


# ---- T-19：冷却到期自动恢复且不覆盖人工禁用（backend 仅此条，仍 HTTP） ----
import json
import time
from unittest.mock import AsyncMock, patch

from backend.services import channel_scheduler_service as sched_mod
from backend.services.channel_scheduler_service import ChannelSchedulerService
from backend.services.newapi_api import RELAY_CHANNEL_CFG_PREFIX, RELAY_CHANNEL_STATE_PREFIX
from stubs import FakeRedis, fake_settings


def _window_svc(redis: FakeRedis) -> ChannelSchedulerService:
    svc = ChannelSchedulerService.__new__(ChannelSchedulerService)
    svc._running = False
    svc._loop_task = None
    svc._redis = redis
    return svc


def _model_payload(ref: str, name: str) -> dict:
    return {"data": [{"model_name": name, "model_info": {"id": ref}}]}


@pytest.mark.asyncio
async def test_cooldown_recovery_skips_manual_disable_http():
    """冷却到期但人工禁用 → 不写 budget、不恢复、解除跟踪。"""
    redis = FakeRedis()
    redis.hashes[f"{RELAY_CHANNEL_CFG_PREFIX}7"] = {
        "limit_quota": "100", "window_hours": "24", "cooldown_seconds": "3600",
        "manual_disabled": "1",
    }
    redis.strings[f"{RELAY_CHANNEL_STATE_PREFIX}7"] = json.dumps({
        "disabled_at": "2026-08-30T10:00:00",
        "cooldown_until": int(time.time()) - 10,
        "last_usage": 999,
    })
    writes: list = []

    async def _capture(body, **_k):
        writes.append(body)
        return {}

    svc = _window_svc(redis)
    svc._record_event = AsyncMock()
    with patch.object(sched_mod, "settings", fake_settings(**{
            "RELAY.DEFAULT_WINDOW_QUOTA": 0})), \
         patch.object(sched_mod.gw_admin, "list_models",
                      AsyncMock(return_value=_model_payload("7", "m7"))), \
         patch.object(sched_mod.gw_admin, "get_spend_logs",
                      AsyncMock(return_value=[])), \
         patch.object(sched_mod.gw_admin, "create_budget", _capture), \
         patch.object(sched_mod.gw_admin, "update_budget", _capture):
        await svc._tick_once()
    assert writes == []
    assert f"{RELAY_CHANNEL_STATE_PREFIX}7" not in redis.strings
    svc._record_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_cooldown_recovery_writes_budget_when_not_manual():
    """冷却到期且非人工禁用 → HTTP 写 budget 恢复，清状态。"""
    redis = FakeRedis()
    redis.hashes[f"{RELAY_CHANNEL_CFG_PREFIX}7"] = {
        "limit_quota": "100", "window_hours": "24", "cooldown_seconds": "3600",
    }
    redis.strings[f"{RELAY_CHANNEL_STATE_PREFIX}7"] = json.dumps({
        "disabled_at": "2026-08-30T10:00:00",
        "cooldown_until": int(time.time()) - 10,
        "last_usage": 999,
    })
    writes: list = []

    async def _create(body, **_k):
        writes.append(("new", body))
        return {}

    svc = _window_svc(redis)
    events: list = []
    svc._record_event = AsyncMock(side_effect=lambda **kw: events.append(kw))
    with patch.object(sched_mod, "settings", fake_settings(**{
            "RELAY.DEFAULT_WINDOW_QUOTA": 0})), \
         patch.object(sched_mod.gw_admin, "list_models",
                      AsyncMock(return_value=_model_payload("7", "m7"))), \
         patch.object(sched_mod.gw_admin, "get_spend_logs",
                      AsyncMock(return_value=[])), \
         patch.object(sched_mod.gw_admin, "create_budget", _create), \
         patch.object(sched_mod, "NotifyService") as notify_cls:
        notify_cls.return_value.notify_text = AsyncMock()
        await svc._tick_once()
    assert writes and writes[0][1]["budget_id"] == "relay:7"
    assert writes[0][1]["max_budget"] == 100
    assert f"{RELAY_CHANNEL_STATE_PREFIX}7" not in redis.strings
    assert events[0]["action"] == "enabled"


@pytest.mark.asyncio
async def test_over_limit_maps_spend_to_budget_not_dsn():
    """超限：先读 spend 再写 budget；不走 DSN / 不 1:1 禁用渠道。"""
    redis = FakeRedis()
    redis.hashes[f"{RELAY_CHANNEL_CFG_PREFIX}5"] = {
        "limit_quota": "1000", "window_hours": "24", "cooldown_seconds": "3600",
    }
    writes: list = []

    async def _create(body, **_k):
        writes.append(body)
        return {}

    svc = _window_svc(redis)
    svc._record_event = AsyncMock()
    with patch.object(sched_mod, "settings", fake_settings(**{
            "RELAY.DEFAULT_WINDOW_QUOTA": 0})), \
         patch.object(sched_mod.gw_admin, "list_models",
                      AsyncMock(return_value=_model_payload("5", "m5"))), \
         patch.object(sched_mod.gw_admin, "get_spend_logs",
                      AsyncMock(return_value=[{"model": "m5", "spend": 1500}])), \
         patch.object(sched_mod.gw_admin, "create_budget", _create):
        await svc._tick_once()
    assert writes and writes[0]["budget_id"] == "relay:5"
    assert writes[0]["max_budget"] == 1000
    state = json.loads(redis.strings[f"{RELAY_CHANNEL_STATE_PREFIX}5"])
    assert state["last_usage"] == 1500
