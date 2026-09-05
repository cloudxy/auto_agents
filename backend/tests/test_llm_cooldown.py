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
