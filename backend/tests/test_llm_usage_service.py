"""LLM token 用量服务单测（P0-3：Redis 聚合计数 + 定时落库）

约定：不连真实 Redis/DB——redis 用 stubs.FakeRedis（经 patch 注入
get_async_redis），落库经 patch 替换 Repository/AsyncSession；测试态
_IN_PYTEST 守卫用 patch 显式翻转以覆盖两条分支。
"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import backend.services.llm_usage_service as usage_mod
from backend.services.llm_usage_service import (
    LlmUsageFlushService,
    _daily_key,
    _monthly_key,
    get_month_used,
    record_usage,
)
from stubs import FakeRedis


# ---------------- record_usage：日/月双计数 ----------------
@pytest.mark.asyncio
async def test_record_usage_increments_daily_and_monthly():
    redis = FakeRedis()
    with patch.object(usage_mod, "_IN_PYTEST", False), \
         patch.object(usage_mod, "get_async_redis", lambda: redis):
        await record_usage("provider:9", "gpt-4o-mini",
                           prompt_tokens=10, completion_tokens=5, total_tokens=15)
        await record_usage("provider:9", "gpt-4o-mini", total_tokens=7)

    today = date.today()
    daily = _daily_key(today)
    fields = redis.hashes[daily]
    assert fields["default|provider:9|gpt-4o-mini|total"] == "22"      # 15 + 7
    assert fields["default|provider:9|gpt-4o-mini|prompt"] == "10"
    assert fields["default|provider:9|gpt-4o-mini|completion"] == "5"
    assert fields["default|provider:9|gpt-4o-mini|requests"] == "2"

    monthly = redis.hashes[_monthly_key(today)]
    assert monthly["provider:9|total"] == "22"                  # 预算读数口径


@pytest.mark.asyncio
async def test_record_usage_noop_in_pytest_mode():
    """测试态守卫：默认 _IN_PYTEST=True 时不触 Redis（llm_client 内存语义零回归）"""
    with patch.object(usage_mod, "get_async_redis", MagicMock(side_effect=AssertionError("不应触网"))):
        await record_usage("config", "m", total_tokens=1)  # 直接返回，不抛


@pytest.mark.asyncio
async def test_record_usage_swallows_redis_failure():
    """Redis 故障：记录失败不向上抛（LLM 主路径不受影响）"""
    def _boom():
        raise RuntimeError("redis down")

    with patch.object(usage_mod, "_IN_PYTEST", False), \
         patch.object(usage_mod, "get_async_redis", _boom):
        await record_usage("config", "m", total_tokens=3)  # 不抛即通过


# ---------------- get_month_used：预算读数与回退 ----------------
@pytest.mark.asyncio
async def test_get_month_used_returns_value_and_zero():
    redis = FakeRedis()
    redis.hashes[_monthly_key(date.today())] = {"default|provider:9|total": "123"}
    with patch.object(usage_mod, "_IN_PYTEST", False), \
         patch.object(usage_mod, "get_async_redis", lambda: redis):
        assert await get_month_used("provider:9") == 123
        assert await get_month_used("provider:404") == 0      # 无记录 = 0


@pytest.mark.asyncio
async def test_get_month_used_none_on_failure_for_memory_fallback():
    """Redis 不可用/测试态 → None（调用方 llm_client 回退进程内存计数）"""
    def _boom():
        raise RuntimeError("redis down")

    with patch.object(usage_mod, "_IN_PYTEST", False), \
         patch.object(usage_mod, "get_async_redis", _boom):
        assert await get_month_used("config") is None
    # 测试态守卫默认分支同样返回 None
    assert await get_month_used("config") is None


# ---------------- _build_rows：hash 字段 → upsert 行 ----------------
def test_build_rows_groups_by_dim_and_model():
    fields = {
        "provider:9|gpt-a|total": "100",
        "provider:9|gpt-a|prompt": "60",
        "provider:9|gpt-a|completion": "40",
        "provider:9|gpt-a|requests": "3",
        "provider:9|gpt-a|failed": "1",
        "provider:9|gpt-b|total": "50",
        "config|gpt-a|total": "7",
        "bad-field": "1",                # 非 3 段：跳过
        "provider:9|gpt-c|unknown": "1", # 未知指标：跳过
        "provider:9|gpt-d|total": "x",   # 非整数：按 0 容错
    }
    rows = {(r["provider_name"], r["model"]): r for r in LlmUsageFlushService._build_rows(fields, date(2026, 8, 31))}

    a = rows[("provider:9", "gpt-a")]
    assert a["provider_id"] == 9
    assert (a["total_tokens"], a["prompt_tokens"], a["completion_tokens"]) == (100, 60, 40)
    assert (a["request_count"], a["failed_count"]) == (3, 1)

    cfg = rows[("config", "gpt-a")]
    assert cfg["provider_id"] is None
    assert cfg["total_tokens"] == 7

    assert rows[("provider:9", "gpt-b")]["total_tokens"] == 50
    assert rows[("provider:9", "gpt-d")]["total_tokens"] == 0  # 坏值容错
    assert len(rows) == 4  # bad-field / unknown 指标被跳过


# ---------------- flush_once：认领-落库-删除链路 ----------------
class _FakeSessionCtx:
    """AsyncSession 上下文桩：仅承载 upsert 调用与 commit"""
    committed = []

    def __init__(self, engine):
        pass

    async def __aenter__(self):
        s = MagicMock()
        s.commit = AsyncMock(side_effect=lambda: _FakeSessionCtx.committed.append(True))
        return s

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_flush_once_persists_rows_and_deletes_claimed_keys():
    redis = FakeRedis()
    redis.hashes[_daily_key(date(2026, 8, 31))] = {
        "default|provider:9|gpt-a|total": "100",
        "default|provider:9|gpt-a|requests": "2",
    }
    svc = LlmUsageFlushService()
    svc._redis = redis

    upsert = AsyncMock(return_value=1)
    repo_cls = MagicMock(return_value=MagicMock(upsert_daily=upsert))
    # 自洽修复：该测试曾顺序耦合于其它测试初始化 DBManager（单跑必 KeyError DEFAULT）；
    # 显式 patch _engine 注入假引擎键，消除顺序依赖
    async def _fake_default_tid(session):
        return 1

    with patch.object(usage_mod, "LlmTokenUsageRepository", repo_cls), \
         patch.object(usage_mod, "AsyncSession", _FakeSessionCtx), \
         patch.object(usage_mod.LlmUsageFlushService, "_engine",
                      staticmethod(lambda: object())), \
         patch("backend.services.background_session.default_tenant_id", _fake_default_tid):
        rows = await svc.flush_once()

    assert rows == 1
    # 行内容：日期解析自键名，数值类型正确
    row = upsert.await_args.args[0][0]
    assert row["provider_name"] == "provider:9"
    assert row["model"] == "gpt-a"
    assert row["stat_date"] == date(2026, 8, 31)
    assert row["total_tokens"] == 100 and row["request_count"] == 2
    assert row["tenant_id"] == 1  # legacy 三段 → 默认租户解析
    # 认领键与原键都已删除（ack 语义）
    assert not redis.hashes


@pytest.mark.asyncio
async def test_flush_once_no_keys_returns_zero():
    svc = LlmUsageFlushService()
    svc._redis = FakeRedis()
    with patch.object(usage_mod, "LlmTokenUsageRepository",
                      MagicMock(side_effect=AssertionError("无键不应落库"))):
        assert await svc.flush_once() == 0
