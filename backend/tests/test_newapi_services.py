"""阶段三单测 - new-api 渠道调度器 + 真伪探针服务

约定：不连真实 MySQL/Redis/new-api，外部依赖全部打桩：
- new-api 管理 API / 采集 API：httpx.MockTransport（验证 HTTP 契约）或 Fake 客户端
- Redis：内存 Fake（SET NX / GET / DEL / HGETALL / HSET 语义）
- new-api 库 engine：Fake sessionmaker（execute 返回预设行或异常序列）
- 主库落库：patch _main_async_session 为 Fake 上下文会话（验证 ORM 字段映射）

覆盖：
- 用量聚合 SQL 生成（unix/datetime 两分支）+ 列类型探测 + 模式翻转重试
- 超限判定与禁用调用（PUT body={"id",status=auto_disabled}）+ 全局默认配置路径
- 冷却恢复且人工禁用不被覆盖 / 冷却期内人工启用解除跟踪
- 单渠道异常隔离（整轮继续）
- 探针判定 original/spoofed/offline 三分支 + 逐字缓存指纹 + 参考相似度
- 事件/探针结果落库字段映射；开关关闭时不启动
- new-api 客户端 HTTP 契约（Bearer 头 / New-Api-User / 分页 / chat 解析）
"""
import json
import time
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.repositories.newapi_repository import (
    ChannelEventRepository,
    ChannelProbeResultRepository,
)
from backend.services import channel_probe_service as probe_mod
from backend.services import channel_scheduler_service as sched_mod
from backend.services import newapi_api as newapi_api_mod
from backend.services.channel_probe_service import (
    DEFAULT_PROBE_QUESTIONS,
    ChannelProbeService,
    _load_questions,
    _score_probe_batch,
)
from backend.services.channel_scheduler_service import (
    ChannelSchedulerService,
    _build_usage_window,
    _is_type_mismatch_error,
)
from backend.services.newapi_api import (
    CHANNEL_STATUS_AUTO_DISABLED,
    CHANNEL_STATUS_ENABLED,
    CHANNEL_STATUS_MANUALLY_DISABLED,
    NEWAPI_CHANNEL_CFG_PREFIX,
    NEWAPI_CHANNEL_STATE_PREFIX,
    NewapiApiClient,
)
from platform_core.models.channel_event import ChannelEvent
from platform_core.models.channel_probe_result import ChannelProbeResult


# ---------------- 测试桩 ----------------
def _fake_settings(**kv) -> MagicMock:
    """settings.get(key, default) 桩（另带 REDIS.DEFAULT.URL 属性链）"""
    m = MagicMock()

    def _get(key, default=None):
        return kv.get(key, default)

    m.get.side_effect = _get
    m.REDIS.DEFAULT.URL = "redis-fake-url"
    return m


class _FakeRedis:
    """内存 Redis（调度器/探针用到的子集语义）"""

    def __init__(self):
        self.strings: dict = {}
        self.hashes: dict = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.strings:
            return False
        self.strings[key] = value
        return True

    async def get(self, key):
        return self.strings.get(key)

    async def delete(self, key):
        return self.strings.pop(key, None) is not None

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value

    async def aclose(self):
        pass


class _FakeApiClient:
    """new-api 客户端桩（记录启停调用）"""

    def __init__(self, channels=None, details=None):
        self.channels = channels or []
        self.details = details or {}
        self.status_calls: list[tuple[int, int]] = []

    async def list_channels(self):
        return [dict(c) for c in self.channels]

    async def get_channel(self, channel_id):
        return self.details.get(channel_id)

    async def set_channel_status(self, channel_id, status):
        self.status_calls.append((channel_id, status))
        return True


class _FakeResult:
    """execute 结果桩（all/first）"""

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """async 上下文会话桩（execute 按预设序列出行/异常，并记录调用参数）"""

    def __init__(self, outcomes: list, calls: list):
        self._outcomes = outcomes
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, sql, params=None):
        self._calls.append((str(sql), params))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _FakeResult(outcome)


class _CtxSessionStub:
    """主库会话桩（异步上下文 + add/commit，验证落库字段映射）"""

    def __init__(self):
        self.add = MagicMock()
        self.flush = AsyncMock()
        self.refresh = AsyncMock()
        self.commit = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _scheduler(fake_redis, fake_api, mode: str | None = "unix") -> ChannelSchedulerService:
    """不触发生命周期的调度器实例（依赖注入桩）"""
    svc = ChannelSchedulerService.__new__(ChannelSchedulerService)
    svc._running = False
    svc._loop_task = None
    svc._redis = fake_redis
    svc._engine = None
    svc._sessionmaker = None
    svc._api = fake_api
    svc._created_at_mode = mode
    return svc


def _probe(fake_redis, fake_api) -> ChannelProbeService:
    """不触发生命周期的探针实例"""
    svc = ChannelProbeService.__new__(ChannelProbeService)
    svc._running = False
    svc._loop_task = None
    svc._redis = fake_redis
    svc._api = fake_api
    return svc


def _cfg_hash(redis: _FakeRedis, cid: int, limit: int = 1000,
              window: int = 24, cooldown: int = 3600) -> None:
    redis.hashes[f"{NEWAPI_CHANNEL_CFG_PREFIX}{cid}"] = {
        "limit_quota": str(limit), "window_hours": str(window),
        "cooldown_seconds": str(cooldown),
    }


# ---------------- 用量聚合 SQL（unix/datetime 两分支） ----------------
class TestUsageSql:
    def test_unix_mode_binds_int(self):
        now = datetime(2026, 8, 30, 12, 0, 0)
        sql, params = _build_usage_window("unix", 24, now=now)
        assert "FROM logs" in sql and "created_at >= :since" in sql
        assert "GROUP BY channel_id" in sql
        assert "total_quota" in sql  # 规避 MySQL 保留字 USAGE
        assert params["since"] == int(datetime(2026, 8, 29, 12, 0, 0).timestamp())
        assert isinstance(params["since"], int)

    def test_datetime_mode_pushes_window_to_sql(self):
        """datetime 模式（评审 m-3）：窗口起点下推 DB 侧 NOW() - INTERVAL，
        绑定整型小时数，消除应用服务器本地时区偏差"""
        now = datetime(2026, 8, 30, 12, 0, 0)
        sql, params = _build_usage_window("datetime", 24, now=now)
        assert "NOW() - INTERVAL :hours HOUR" in sql
        assert "GROUP BY channel_id" in sql
        assert params == {"hours": 24}

    @pytest.mark.asyncio
    async def test_fetch_usage_flips_mode_on_failure(self):
        """「参数类型不匹配」错误时 unix→datetime 翻转重试一次并缓存新模式"""
        svc = _scheduler(_FakeRedis(), _FakeApiClient(), mode="unix")
        calls: list = []
        outcomes = [RuntimeError("type mismatch"), [(5, 1500)]]  # 共享序列：跨会话弹出
        svc._sessionmaker = lambda: _FakeSession(outcomes, calls)
        usage = await svc._fetch_usage(24)
        assert usage == {5: 1500}
        assert svc._created_at_mode == "datetime"
        assert calls[1][1]["hours"] == 24  # 翻转后为 datetime 模式（SQL 侧 NOW() - INTERVAL）

    @pytest.mark.asyncio
    async def test_fetch_usage_raises_on_other_errors(self):
        """评审 m-2：非类型不匹配错误（如网络/服务故障）不翻转不缓存，直接抛出"""
        svc = _scheduler(_FakeRedis(), _FakeApiClient(), mode="unix")
        svc._sessionmaker = lambda: _FakeSession([RuntimeError("connection refused")], [])
        with pytest.raises(RuntimeError, match="connection refused"):
            await svc._fetch_usage(24)
        assert svc._created_at_mode == "unix"  # 模式未被误翻转缓存

    @pytest.mark.asyncio
    async def test_fetch_usage_clears_cache_when_flip_retry_fails(self):
        """翻转重试仍失败：清空模式缓存（下次重新探测）并抛出"""
        svc = _scheduler(_FakeRedis(), _FakeApiClient(), mode="unix")
        outcomes = [RuntimeError("type mismatch"), RuntimeError("illegal mix")]  # 共享序列：跨会话弹出
        svc._sessionmaker = lambda: _FakeSession(outcomes, [])
        with pytest.raises(RuntimeError):
            await svc._fetch_usage(24)
        assert svc._created_at_mode is None

    def test_type_mismatch_error_detection(self):
        """类型不匹配特征判定（DataError / 关键词匹配）"""
        from sqlalchemy.exc import DataError

        assert _is_type_mismatch_error(RuntimeError("type mismatch")) is True
        assert _is_type_mismatch_error(RuntimeError("Illegal mix of collations")) is True
        assert _is_type_mismatch_error(RuntimeError("Truncated incorrect INTEGER")) is True
        assert _is_type_mismatch_error(DataError("stmt", {}, Exception("22001"))) is True
        assert _is_type_mismatch_error(RuntimeError("connection refused")) is False
        assert _is_type_mismatch_error(RuntimeError("timeout")) is False

    @pytest.mark.asyncio
    async def test_fetch_usage_gives_up_after_retry(self):
        """类型不匹配翻转重试后仍失败 → 异常抛给上层（不再静默返回空）"""
        svc = _scheduler(_FakeRedis(), _FakeApiClient(), mode="unix")
        outcomes = [RuntimeError("type mismatch"),
                    RuntimeError("still type mismatch")]  # 共享序列：跨会话弹出
        svc._sessionmaker = lambda: _FakeSession(outcomes, [])
        with pytest.raises(RuntimeError, match="still type mismatch"):
            await svc._fetch_usage(24)
        assert svc._created_at_mode is None

    @pytest.mark.asyncio
    async def test_ensure_created_at_mode_probes_schema(self):
        cases = [([[("datetime",)]], "datetime"), ([[("bigint",)]], "unix"),
                 ([[("int",)]], "unix")]
        for outcomes, expected in cases:
            svc = _scheduler(_FakeRedis(), _FakeApiClient(), mode=None)
            svc._sessionmaker = lambda outcomes=outcomes: _FakeSession(list(outcomes), [])
            assert await svc._ensure_created_at_mode() == expected

    @pytest.mark.asyncio
    async def test_ensure_created_at_mode_falls_back_to_unix(self):
        svc = _scheduler(_FakeRedis(), _FakeApiClient(), mode=None)
        svc._sessionmaker = lambda: _FakeSession([RuntimeError("no schema")], [])
        assert await svc._ensure_created_at_mode() == "unix"


# ---------------- 调度器：超限禁用 / 冷却恢复 / 隔离 ----------------
GLOBAL_OFF = {"NEWAPI.DEFAULT_WINDOW_QUOTA": 0}


class TestSchedulerFlow:
    @pytest.mark.asyncio
    async def test_over_limit_disables_channel_and_records_event(self):
        redis = _FakeRedis()
        _cfg_hash(redis, 5, limit=1000)
        api = _FakeApiClient(channels=[{"id": 5, "name": "prov-a", "status": CHANNEL_STATUS_ENABLED}])
        svc = _scheduler(redis, api)
        svc._sessionmaker = lambda: _FakeSession([[(5, 1500)]], [])
        events: list = []
        svc._record_event = AsyncMock(side_effect=lambda **kw: events.append(kw))
        with patch.object(sched_mod, "settings", _fake_settings(**GLOBAL_OFF)):
            await svc._tick_once()
        # PUT 禁用（status=auto_disabled，与人工禁用 2 区分）
        assert api.status_calls == [(5, CHANNEL_STATUS_AUTO_DISABLED)]
        state = json.loads(redis.strings[f"{NEWAPI_CHANNEL_STATE_PREFIX}5"])
        assert state["last_usage"] == 1500
        assert state["cooldown_until"] >= int(time.time()) + 3500
        assert state["disabled_at"]
        assert events[0]["channel_id"] == 5 and events[0]["action"] == "disabled"
        assert events[0]["usage"] == 1500 and events[0]["limit_quota"] == 1000
        assert events[0]["window_hours"] == 24 and events[0]["source"] == "scheduler"

    @pytest.mark.asyncio
    async def test_within_limit_keeps_channel(self):
        redis = _FakeRedis()
        _cfg_hash(redis, 5, limit=1000)
        api = _FakeApiClient(channels=[{"id": 5, "name": "prov-a", "status": CHANNEL_STATUS_ENABLED}])
        svc = _scheduler(redis, api)
        svc._sessionmaker = lambda: _FakeSession([[(5, 500)]], [])
        svc._record_event = AsyncMock()
        with patch.object(sched_mod, "settings", _fake_settings(**GLOBAL_OFF)):
            await svc._tick_once()
        assert api.status_calls == []
        assert f"{NEWAPI_CHANNEL_STATE_PREFIX}5" not in redis.strings

    @pytest.mark.asyncio
    async def test_global_default_applies_without_channel_cfg(self):
        redis = _FakeRedis()
        api = _FakeApiClient(channels=[{"id": 5, "name": "prov-a", "status": CHANNEL_STATUS_ENABLED}])
        svc = _scheduler(redis, api)
        svc._sessionmaker = lambda: _FakeSession([[(5, 2500)]], [])
        events: list = []
        svc._record_event = AsyncMock(side_effect=lambda **kw: events.append(kw))
        with patch.object(sched_mod, "settings", _fake_settings(**{
                "NEWAPI.DEFAULT_WINDOW_QUOTA": 2000,
                "NEWAPI.DEFAULT_WINDOW_HOURS": 24,
                "NEWAPI.DEFAULT_COOLDOWN_SECONDS": 600})):
            await svc._tick_once()
        assert api.status_calls == [(5, CHANNEL_STATUS_AUTO_DISABLED)]
        assert events[0]["limit_quota"] == 2000 and events[0]["window_hours"] == 24

    @pytest.mark.asyncio
    async def test_cooldown_recovery_skips_manual_disable(self):
        """冷却到期但渠道已被人工禁用 → 不覆盖人工操作，解除跟踪且不写恢复事件"""
        redis = _FakeRedis()
        _cfg_hash(redis, 7, limit=100)
        redis.strings[f"{NEWAPI_CHANNEL_STATE_PREFIX}7"] = json.dumps({
            "disabled_at": "2026-08-30T10:00:00",
            "cooldown_until": int(time.time()) - 10,  # 已到期
            "last_usage": 999,
        })
        api = _FakeApiClient(
            channels=[{"id": 7, "name": "prov-b", "status": CHANNEL_STATUS_AUTO_DISABLED}],
            details={7: {"id": 7, "name": "prov-b", "status": CHANNEL_STATUS_MANUALLY_DISABLED}},
        )
        svc = _scheduler(redis, api)
        svc._sessionmaker = lambda: _FakeSession([[(7, 0)]], [])
        svc._record_event = AsyncMock()
        with patch.object(sched_mod, "settings", _fake_settings(**GLOBAL_OFF)):
            await svc._tick_once()
        assert CHANNEL_STATUS_ENABLED not in [s for _cid, s in api.status_calls]
        assert f"{NEWAPI_CHANNEL_STATE_PREFIX}7" not in redis.strings
        svc._record_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cooldown_recovery_enables_after_expiry(self):
        redis = _FakeRedis()
        _cfg_hash(redis, 7, limit=100)
        redis.strings[f"{NEWAPI_CHANNEL_STATE_PREFIX}7"] = json.dumps({
            "disabled_at": "2026-08-30T10:00:00",
            "cooldown_until": int(time.time()) - 10,
            "last_usage": 999,
        })
        api = _FakeApiClient(
            channels=[{"id": 7, "name": "prov-b", "status": CHANNEL_STATUS_AUTO_DISABLED}],
            details={7: {"id": 7, "name": "prov-b", "status": CHANNEL_STATUS_AUTO_DISABLED}},
        )
        svc = _scheduler(redis, api)
        svc._sessionmaker = lambda: _FakeSession([[(7, 0)]], [])
        events: list = []
        svc._record_event = AsyncMock(side_effect=lambda **kw: events.append(kw))
        with patch.object(sched_mod, "settings", _fake_settings(**GLOBAL_OFF)):
            await svc._tick_once()
        assert api.status_calls == [(7, CHANNEL_STATUS_ENABLED)]
        assert f"{NEWAPI_CHANNEL_STATE_PREFIX}7" not in redis.strings
        assert events[0]["action"] == "enabled" and events[0]["source"] == "scheduler"

    @pytest.mark.asyncio
    async def test_manual_enable_during_cooldown_clears_state(self):
        """冷却期内被人工重新启用 → 解除跟踪，不重复禁用"""
        redis = _FakeRedis()
        _cfg_hash(redis, 7, limit=100)
        redis.strings[f"{NEWAPI_CHANNEL_STATE_PREFIX}7"] = json.dumps({
            "disabled_at": "2026-08-30T10:00:00",
            "cooldown_until": int(time.time()) + 3000,  # 冷却未到期
            "last_usage": 999,
        })
        api = _FakeApiClient(
            channels=[{"id": 7, "name": "prov-b", "status": CHANNEL_STATUS_ENABLED}]
        )
        svc = _scheduler(redis, api)
        svc._sessionmaker = lambda: _FakeSession([[(7, 0)]], [])
        svc._record_event = AsyncMock()
        with patch.object(sched_mod, "settings", _fake_settings(**GLOBAL_OFF)):
            await svc._tick_once()
        assert api.status_calls == []  # 用量未超限（0 < 100），且不覆盖人工启用
        assert f"{NEWAPI_CHANNEL_STATE_PREFIX}7" not in redis.strings

    @pytest.mark.asyncio
    async def test_channel_exception_isolation(self):
        """单渠道异常不中断整轮（蓝本缺陷④规避）"""
        redis = _FakeRedis()
        _cfg_hash(redis, 1)
        _cfg_hash(redis, 2)
        api = _FakeApiClient(channels=[
            {"id": 1, "name": "a", "status": CHANNEL_STATUS_ENABLED},
            {"id": 2, "name": "b", "status": CHANNEL_STATUS_ENABLED},
        ])
        svc = _scheduler(redis, api)
        svc._sessionmaker = lambda: _FakeSession([[(1, 0), (2, 0)]], [])
        processed: list = []

        async def fake_process(channel, cfg, usage):
            processed.append(channel["id"])
            if channel["id"] == 1:
                raise RuntimeError("boom")

        svc._process_channel = fake_process
        with patch.object(sched_mod, "settings", _fake_settings(**GLOBAL_OFF)):
            await svc._tick_once()  # 不抛异常
        assert processed == [1, 2]


# ---------------- 调度器：锁释放 / 状态重建 / 禁用前复核 ----------------
class TestSchedulerLockAndGuards:
    @pytest.mark.asyncio
    async def test_lock_released_after_tick(self):
        """评审 m-1：本轮结束后锁主动释放（值比对后删除）"""
        redis = _FakeRedis()
        _cfg_hash(redis, 5, limit=1000)
        api = _FakeApiClient(channels=[{"id": 5, "name": "p", "status": CHANNEL_STATUS_ENABLED}])
        svc = _scheduler(redis, api)
        svc._sessionmaker = lambda: _FakeSession([[(5, 0)]], [])
        with patch.object(sched_mod, "settings", _fake_settings(**GLOBAL_OFF)):
            await svc._tick_once()
        assert sched_mod.NEWAPI_SCHEDULER_LOCK_KEY not in redis.strings

    @pytest.mark.asyncio
    async def test_lock_released_on_early_return(self):
        """评审 m-1：渠道列表为空的早退路径也释放锁"""
        redis = _FakeRedis()
        api = _FakeApiClient(channels=[])
        svc = _scheduler(redis, api)
        with patch.object(sched_mod, "settings", _fake_settings(**GLOBAL_OFF)):
            await svc._tick_once()
        assert sched_mod.NEWAPI_SCHEDULER_LOCK_KEY not in redis.strings

    @pytest.mark.asyncio
    async def test_lock_released_when_tick_raises(self):
        """评审 m-1：list_channels 抛异常时 finally 仍释放锁"""
        redis = _FakeRedis()
        api = MagicMock()
        api.list_channels = AsyncMock(side_effect=RuntimeError("boom"))
        svc = _scheduler(redis, api)
        with patch.object(sched_mod, "settings", _fake_settings(**GLOBAL_OFF)):
            with pytest.raises(RuntimeError, match="boom"):
                await svc._tick_once()
        assert sched_mod.NEWAPI_SCHEDULER_LOCK_KEY not in redis.strings

    @pytest.mark.asyncio
    async def test_release_lock_only_deletes_own_token(self):
        """值比对：token 不匹配（已被他实例接管）时不删除"""
        redis = _FakeRedis()
        svc = _scheduler(redis, _FakeApiClient())
        redis.strings[sched_mod.NEWAPI_SCHEDULER_LOCK_KEY] = "other-token"
        await svc._release_lock(sched_mod.NEWAPI_SCHEDULER_LOCK_KEY, "my-token")
        assert redis.strings[sched_mod.NEWAPI_SCHEDULER_LOCK_KEY] == "other-token"
        await svc._release_lock(sched_mod.NEWAPI_SCHEDULER_LOCK_KEY, "other-token")
        assert sched_mod.NEWAPI_SCHEDULER_LOCK_KEY not in redis.strings

    @pytest.mark.asyncio
    async def test_state_missing_rebuilds_with_default_cooldown(self):
        """评审 m-4：status=3 但 Redis 状态丢失 → 按默认 cooldown 重建 + 落事件"""
        redis = _FakeRedis()
        _cfg_hash(redis, 9, limit=100, cooldown=1800)
        api = _FakeApiClient(
            channels=[{"id": 9, "name": "p", "status": CHANNEL_STATUS_AUTO_DISABLED}]
        )
        svc = _scheduler(redis, api)
        svc._sessionmaker = lambda: _FakeSession([[(9, 0)]], [])
        events: list = []
        svc._record_event = AsyncMock(side_effect=lambda **kw: events.append(kw))
        with patch.object(sched_mod, "settings", _fake_settings(**GLOBAL_OFF)):
            await svc._tick_once()
        # 不静默 return：状态已重建（默认冷却）且落事件留痕
        state = json.loads(redis.strings[f"{NEWAPI_CHANNEL_STATE_PREFIX}9"])
        assert state["cooldown_until"] >= int(time.time()) + 1700
        assert state["disabled_at"]
        assert events[0]["action"] == "state_rebuilt"
        assert events[0]["source"] == "scheduler"
        assert events[0]["reason"] == "state rebuilt"
        assert api.status_calls == []  # 未做启停操作

    @pytest.mark.asyncio
    async def test_disable_channel_rechecks_manual_disable(self):
        """评审 m-8：PUT 前 GET 复核发现人工禁用(status=2) → 跳过并落事件"""
        redis = _FakeRedis()
        _cfg_hash(redis, 5, limit=1000)
        api = _FakeApiClient(
            channels=[{"id": 5, "name": "p", "status": CHANNEL_STATUS_ENABLED}],
            details={5: {"id": 5, "name": "p", "status": CHANNEL_STATUS_MANUALLY_DISABLED}},
        )
        svc = _scheduler(redis, api)
        svc._sessionmaker = lambda: _FakeSession([[(5, 1500)]], [])
        events: list = []
        svc._record_event = AsyncMock(side_effect=lambda **kw: events.append(kw))
        with patch.object(sched_mod, "settings", _fake_settings(**GLOBAL_OFF)):
            await svc._tick_once()
        assert api.status_calls == []  # 未 PUT 禁用
        assert f"{NEWAPI_CHANNEL_STATE_PREFIX}5" not in redis.strings
        assert events[0]["action"] == "disable_skipped"
        assert events[0]["usage"] == 1500

    @pytest.mark.asyncio
    async def test_disable_channel_proceeds_when_recheck_ok(self):
        """评审 m-8：复核状态仍启用（或 GET 失败）→ 正常禁用路径不受影响"""
        redis = _FakeRedis()
        _cfg_hash(redis, 5, limit=1000)
        api = _FakeApiClient(
            channels=[{"id": 5, "name": "p", "status": CHANNEL_STATUS_ENABLED}],
            details={5: {"id": 5, "name": "p", "status": CHANNEL_STATUS_ENABLED}},
        )
        svc = _scheduler(redis, api)
        svc._sessionmaker = lambda: _FakeSession([[(5, 1500)]], [])
        svc._record_event = AsyncMock()
        with patch.object(sched_mod, "settings", _fake_settings(**GLOBAL_OFF)):
            await svc._tick_once()
        assert api.status_calls == [(5, CHANNEL_STATUS_AUTO_DISABLED)]


# ---------------- 调度器/探针：开关与生命周期 ----------------
class TestSwitches:
    @pytest.mark.asyncio
    async def test_scheduler_disabled_when_switch_off(self):
        svc = _scheduler(_FakeRedis(), _FakeApiClient(), mode=None)
        with patch.object(sched_mod, "settings", _fake_settings(**{"NEWAPI.ENABLED": False})):
            await svc.start()
        assert not svc._running and svc._loop_task is None
        with patch.object(sched_mod, "settings", _fake_settings(
                **{"NEWAPI.ENABLED": True, "NEWAPI.SCHEDULER_ENABLED": False})):
            await svc.start()
        assert not svc._running and svc._loop_task is None

    @pytest.mark.asyncio
    async def test_scheduler_start_and_stop(self):
        fake_client = _FakeApiClient(channels=[])
        with patch.object(sched_mod, "settings", _fake_settings(**{
                "NEWAPI.ENABLED": True, "NEWAPI.SCHEDULER_ENABLED": True,
                "NEWAPI.DB_DSN": "async+driver://user:pass@newapi-db.internal:3306/new_api_db",
                "NEWAPI.INTERVAL_SECONDS": 3600})), \
             patch.object(sched_mod, "aioredis") as fake_aioredis, \
             patch.object(sched_mod, "create_async_engine", return_value=AsyncMock()), \
             patch.object(sched_mod, "NewapiApiClient", return_value=fake_client):
            fake_aioredis.from_url.return_value = _FakeRedis()
            svc = ChannelSchedulerService()
            await svc.start()
            assert svc._running is True
            assert svc._loop_task is not None
            await svc.stop()
        assert svc._running is False and svc._loop_task is None

    @pytest.mark.asyncio
    async def test_scheduler_requires_db_dsn(self):
        svc = _scheduler(_FakeRedis(), _FakeApiClient(), mode=None)
        with patch.object(sched_mod, "settings", _fake_settings(
                **{"NEWAPI.ENABLED": True, "NEWAPI.SCHEDULER_ENABLED": True})):
            await svc.start()
        assert not svc._running

    @pytest.mark.asyncio
    async def test_probe_disabled_when_switch_off(self):
        svc = _probe(_FakeRedis(), _FakeApiClient())
        with patch.object(probe_mod, "settings", _fake_settings(**{"NEWAPI.ENABLED": False})):
            await svc.start()
        assert not svc._running and svc._loop_task is None
        with patch.object(probe_mod, "settings", _fake_settings(
                **{"NEWAPI.ENABLED": True, "NEWAPI.PROBE_ENABLED": False})):
            await svc.start()
        assert not svc._running and svc._loop_task is None

    @pytest.mark.asyncio
    async def test_probe_start_and_stop(self):
        fake_client = _FakeApiClient(channels=[])
        with patch.object(probe_mod, "settings", _fake_settings(**{
                "NEWAPI.ENABLED": True, "NEWAPI.PROBE_ENABLED": True,
                "NEWAPI.PROBE_INTERVAL_SECONDS": 3600})), \
             patch.object(probe_mod, "aioredis") as fake_aioredis, \
             patch.object(probe_mod, "NewapiApiClient", return_value=fake_client):
            fake_aioredis.from_url.return_value = _FakeRedis()
            svc = ChannelProbeService()
            await svc.start()
            assert svc._running is True
            await svc.stop()
        assert svc._running is False


# ---------------- 探针判定三分支 ----------------
def _resp(content="ok", ok=True, latency=800, model="gpt-4o", usage=None,
          reasoning=0, error=None) -> dict:
    return {"ok": ok, "content": content, "latency_ms": latency, "model": model,
            "usage": usage if usage is not None else {"total_tokens": 20},
            "reasoning_tokens": reasoning, "error": error}


def _results(**overrides) -> dict:
    base = {
        "identity_zh": _resp("我是 gpt-4o 模型"),
        "identity_en": _resp("I am gpt-4o."),
        "knowledge_cutoff_zh": _resp("2025 年 3 月发生了某发布会"),
        "knowledge_cutoff_en": _resp("In March 2025 an event happened"),
        "math_reasoning": _resp("10145"),
        "instruction_following": _resp("RED\nBLUE"),
        "knowledge_cutoff_zh:repeat": _resp("2025 年 6 月另有事件"),
        "instruction_following:repeat1": _resp("RED\nBLUE"),
        "instruction_following:repeat2": _resp("RED\nBLUE"),
    }
    base.update(overrides)
    return base


class TestProbeVerdict:
    def test_original_when_all_signals_clean(self):
        verdict, scores = _score_probe_batch("gpt-4o", _results(), DEFAULT_PROBE_QUESTIONS)
        assert verdict == "original"
        assert scores["identity"] == 1.0
        assert scores["zh_en_consistency"] == 1.0
        assert scores["math_reasoning"] == 1.0
        assert scores["instruction_following"] == 1.0
        assert scores["verbatim_repeat"] == 1.0
        assert scores["format_stability"] == 1.0
        assert scores["reasoning_tokens_anomaly"] == 1.0

    def test_spoofed_by_identity_contradiction(self):
        r = _results(identity_zh=_resp("我是 GLM-4"), identity_en=_resp("I am GLM-4."))
        verdict, scores = _score_probe_batch("gpt-4o", r, DEFAULT_PROBE_QUESTIONS)
        assert verdict == "spoofed"
        assert scores["identity"] == 0.0

    def test_unknown_family_not_spoofed_by_identity_contradiction(self):
        """评审 m-6：请求模型家族无法识别时，身份回答提及已知家族词
        不判 spoofed（scores 保留记录，供人工复核）"""
        r = _results(identity_zh=_resp("我是 GLM-4"), identity_en=_resp("I am GLM-4."))
        verdict, scores = _score_probe_batch("some-unknown-model-x", r, DEFAULT_PROBE_QUESTIONS)
        assert verdict == "original"  # 不再误判 spoofed
        assert scores["identity"] == 0.0  # 低分仅记录

    def test_known_family_still_spoofed_by_contradiction(self):
        """评审 m-6 回归：已知家族的身份矛盾仍正常判 spoofed"""
        r = _results(identity_zh=_resp("我是 GLM-4"), identity_en=_resp("I am GLM-4."))
        verdict, scores = _score_probe_batch("gpt-4o", r, DEFAULT_PROBE_QUESTIONS)
        assert verdict == "spoofed"
        assert scores["identity"] == 0.0

    def test_spoofed_by_verbatim_cache_fingerprint(self):
        """同题逐字重复（缓存指纹）→ spoofed"""
        r = _results(**{"knowledge_cutoff_zh:repeat": _resp("2025 年 3 月发生了某发布会")})
        verdict, scores = _score_probe_batch("gpt-4o", r, DEFAULT_PROBE_QUESTIONS)
        assert verdict == "spoofed"
        assert scores["verbatim_repeat"] == 0.0

    def test_spoofed_by_low_reference_similarity(self):
        ref = _results(identity_zh=_resp("甲乙丙丁戊己庚辛"),
                       identity_en=_resp("Totally different reference answer"),
                       knowledge_cutoff_zh=_resp("壬癸子丑寅卯辰巳"),
                       knowledge_cutoff_en=_resp("No similarity at all here"),
                       math_reasoning=_resp("99999"),
                       instruction_following=_resp("XXX\nYYY"))
        verdict, scores = _score_probe_batch(
            "gpt-4o", _results(), DEFAULT_PROBE_QUESTIONS, ref_results=ref)
        assert verdict == "spoofed"
        assert scores["ref_similarity"] < 0.15

    def test_offline_when_majority_calls_fail(self):
        r = {k: _resp(ok=False, error="timeout") for k in _results()}
        verdict, scores = _score_probe_batch("gpt-4o", r, DEFAULT_PROBE_QUESTIONS)
        assert verdict == "offline"
        assert scores == {"total_calls": 9, "ok_calls": 0}

    def test_reasoning_tokens_anomaly_on_non_o_series(self):
        r = _results(identity_zh=_resp("我是 gpt-4o 模型", reasoning=128))
        _, scores = _score_probe_batch("gpt-4o", r, DEFAULT_PROBE_QUESTIONS)
        assert scores["reasoning_tokens_anomaly"] == 0.0
        # o 系模型返回 reasoning_tokens 属正常
        r2 = _results(identity_zh=_resp("我是 o3", reasoning=128))
        _, scores2 = _score_probe_batch("o3", r2, DEFAULT_PROBE_QUESTIONS)
        assert scores2["reasoning_tokens_anomaly"] == 1.0

    def test_low_latency_ratio_against_reference(self):
        ref = _results()
        r = _results(identity_zh=_resp("我是 gpt-4o 模型", latency=10))
        _, scores = _score_probe_batch("gpt-4o", r, DEFAULT_PROBE_QUESTIONS, ref_results=ref)
        assert scores["latency_ratio"] < 0.2
        assert scores["latency"] == 0.5

    def test_price_anomaly_on_missing_usage(self):
        r = _results(identity_zh=_resp("我是 gpt-4o 模型", usage={}))
        _, scores = _score_probe_batch("gpt-4o", r, DEFAULT_PROBE_QUESTIONS)
        assert scores["price_anomaly"] == 0.5


# ---------------- 探针：批次巡检与落库 ----------------
_chat_calls: dict[str, int] = {}


def _fake_chat(model, prompt, timeout=None) -> dict:
    """确定性采集桩；同题重复调用返回略异内容（模拟真实非缓存行为）"""
    answers = [
        ("你是什么模型", "我是 gpt-4o 模型"),
        ("What model are you", "I am gpt-4o."),
        ("2025 年发生的具体事件", "2025 年 6 月举办了发布会"),
        ("Name one specific event", "In June 2025 a launch event happened"),
        ("137 × 89", "10145"),
        ("严格按照以下格式", "RED\nBLUE"),
    ]
    for key, ans in answers:
        if key in prompt:
            _chat_calls[key] = _chat_calls.get(key, 0) + 1
            n = _chat_calls[key]
            return _resp(ans if n == 1 else f"{ans}（补充说明{n}）", model=model)
    return _resp("好的。", model=model)


class TestProbeFlow:
    @pytest.mark.asyncio
    async def test_tick_once_probes_enabled_targets_excluding_reference(self):
        _chat_calls.clear()
        redis = _FakeRedis()
        api = _FakeApiClient(channels=[
            {"id": 1, "name": "ref-ch", "status": CHANNEL_STATUS_ENABLED, "models": "gpt-4o"},
            {"id": 2, "name": "target-a", "status": CHANNEL_STATUS_ENABLED, "models": "gpt-4o-mini"},
            {"id": 3, "name": "disabled", "status": CHANNEL_STATUS_MANUALLY_DISABLED, "models": "qwen-max"},
        ])
        svc = _probe(redis, api)
        svc._api.chat_completion = AsyncMock(side_effect=_fake_chat)
        recorded: list = []
        svc._record_probe_result = AsyncMock(side_effect=lambda **kw: recorded.append(kw))
        with patch.object(probe_mod, "settings", _fake_settings(
                **{"NEWAPI.PROBE_REFERENCE_CHANNEL": "ref-ch"})):
            await svc._tick_once()
        assert [r["channel_id"] for r in recorded] == [2]
        assert recorded[0]["model"] == "gpt-4o-mini"
        assert recorded[0]["verdict"] == "original"
        assert len(recorded[0]["batch_id"]) == 32  # uuid hex
        # 锁已在本批结束时主动释放（评审 m-1，不再残留等待 TTL 过期）
        assert probe_mod.NEWAPI_PROBE_LOCK_KEY not in redis.strings
        # 参考渠道基线已采集（每题 + 复测共 9 次）
        assert svc._api.chat_completion.await_count >= 9

    @pytest.mark.asyncio
    async def test_probe_channel_records_result(self):
        _chat_calls.clear()
        svc = _probe(_FakeRedis(), MagicMock())
        svc._api.chat_completion = AsyncMock(side_effect=_fake_chat)
        recorded: list = []
        svc._record_probe_result = AsyncMock(side_effect=lambda **kw: recorded.append(kw))
        await svc._probe_channel(
            {"id": 9, "name": "prov", "models": "gpt-4o,gpt-4o-mini"},
            None, DEFAULT_PROBE_QUESTIONS, "batch-xyz")
        assert recorded[0]["channel_id"] == 9
        assert recorded[0]["model"] == "gpt-4o"  # models 串首个
        assert recorded[0]["verdict"] == "original"
        assert recorded[0]["batch_id"] == "batch-xyz"
        assert recorded[0]["latency_ms"] == 800
        assert recorded[0]["scores"]["identity"] == 1.0

    @pytest.mark.asyncio
    async def test_probe_channel_without_identity_question(self):
        """评审 m-5：问题集缺失 identity 题时不 KeyError，latency 为 None"""
        questions = [q for q in DEFAULT_PROBE_QUESTIONS if q["category"] != "identity"]
        svc = _probe(_FakeRedis(), MagicMock())
        svc._api.chat_completion = AsyncMock(side_effect=_fake_chat)
        recorded: list = []
        svc._record_probe_result = AsyncMock(side_effect=lambda **kw: recorded.append(kw))
        await svc._probe_channel(
            {"id": 9, "name": "prov", "models": "gpt-4o"},
            None, questions, "batch-no-identity")
        assert len(recorded) == 1
        assert recorded[0]["latency_ms"] is None

    @pytest.mark.asyncio
    async def test_record_probe_result_writes_via_main_session(self, monkeypatch):
        fake_session = _CtxSessionStub()
        monkeypatch.setattr(probe_mod, "_main_async_session", lambda: fake_session)
        svc = _probe(_FakeRedis(), MagicMock())
        await svc._record_probe_result(
            channel_id=9, model="gpt-4o", verdict="spoofed",
            scores={"identity": 0.0}, latency_ms=800, batch_id="b1")
        fake_session.commit.assert_awaited_once()
        added = fake_session.add.call_args.args[0]
        assert isinstance(added, ChannelProbeResult)
        assert added.channel_id == 9 and added.verdict == "spoofed"
        assert added.model == "gpt-4o" and added.batch_id == "b1"

    def test_load_questions_file_override_and_fallback(self, tmp_path):
        qfile = tmp_path / "q.json"
        qfile.write_text(json.dumps({"questions": [
            {"id": "x1", "category": "identity", "text": "你是谁？"},
        ]}), encoding="utf-8")
        qs = _load_questions(str(qfile))
        assert qs[0]["id"] == "x1"
        bad = tmp_path / "bad.json"
        bad.write_text("{not-json", encoding="utf-8")
        assert _load_questions(str(bad)) == DEFAULT_PROBE_QUESTIONS
        assert _load_questions("") == DEFAULT_PROBE_QUESTIONS


# ---------------- 落库字段映射（Repository + 主库会话） ----------------
def _session_stub() -> MagicMock:
    s = MagicMock()
    s.add = MagicMock()
    s.flush = AsyncMock()
    s.refresh = AsyncMock()
    s.execute = AsyncMock()
    return s


class TestRepositories:
    @pytest.mark.asyncio
    async def test_event_repo_create_fields(self):
        session = _session_stub()
        event = await ChannelEventRepository(session).create_event(
            channel_id=5, action="disabled", usage=1500, limit_quota=1000,
            window_hours=24, reason="超限", source="scheduler")
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        assert isinstance(event, ChannelEvent)
        assert event.channel_id == 5 and event.action == "disabled"
        assert event.usage == 1500 and event.limit_quota == 1000
        assert event.window_hours == 24 and event.source == "scheduler"

    @pytest.mark.asyncio
    async def test_event_repo_list_and_count_filters(self):
        session = _session_stub()
        stub = MagicMock()
        stub.scalars.return_value.all.return_value = []
        stub.scalar_one.return_value = 0
        session.execute.return_value = stub
        repo = ChannelEventRepository(session)
        assert await repo.list_events(channel_id=5, action="disabled") == []
        stmt = session.execute.call_args.args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "channel_events" in compiled and "channel_id" in compiled
        assert await repo.count_events(source="scheduler") == 0

    @pytest.mark.asyncio
    async def test_probe_result_repo_create_and_latest(self):
        session = _session_stub()
        repo = ChannelProbeResultRepository(session)
        result = await repo.create_result(
            channel_id=9, model="gpt-4o", verdict="spoofed",
            scores={"identity": 0.0}, latency_ms=800, batch_id="abc")
        session.add.assert_called_once()
        assert isinstance(result, ChannelProbeResult)
        assert result.verdict == "spoofed" and result.batch_id == "abc"
        assert result.scores == {"identity": 0.0} and result.latency_ms == 800

        sentinel = SimpleNamespace(verdict="original")
        stub = MagicMock()
        stub.scalars.return_value.first.return_value = sentinel
        session.execute.return_value = stub
        assert await repo.latest_verdict(9) is sentinel
        compiled = str(session.execute.call_args.args[0].compile(
            compile_kwargs={"literal_binds": True}))
        assert "channel_probe_results" in compiled

    @pytest.mark.asyncio
    async def test_record_event_writes_via_main_session(self, monkeypatch):
        fake_session = _CtxSessionStub()
        monkeypatch.setattr(sched_mod, "_main_async_session", lambda: fake_session)
        svc = _scheduler(_FakeRedis(), _FakeApiClient())
        await svc._record_event(channel_id=5, action="enabled",
                                source="scheduler", reason="冷却到期自动恢复上线")
        fake_session.commit.assert_awaited_once()
        added = fake_session.add.call_args.args[0]
        assert isinstance(added, ChannelEvent)
        assert added.action == "enabled" and added.reason == "冷却到期自动恢复上线"


# ---------------- new-api 客户端 HTTP 契约 ----------------
class TestNewapiApiClient:
    @pytest.mark.asyncio
    async def test_set_channel_status_request_contract(self):
        """PUT /api/channel/ body={id,status} + Bearer 头（蓝本 :158-184 写法）"""
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("Authorization")
            captured["user"] = request.headers.get("New-Api-User")
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"success": True})

        client = NewapiApiClient(
            base_url="http://newapi.test", token="tok-abc",
            transport=httpx.MockTransport(handler))
        assert await client.set_channel_status(5, CHANNEL_STATUS_AUTO_DISABLED) is True
        assert captured["method"] == "PUT"
        assert captured["url"] == "http://newapi.test/api/channel/"
        assert captured["auth"] == "Bearer tok-abc"
        assert captured["body"] == {"id": 5, "status": CHANNEL_STATUS_AUTO_DISABLED}

    @pytest.mark.asyncio
    async def test_set_channel_status_rejected(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": False, "message": "no permission"})

        client = NewapiApiClient(base_url="http://newapi.test", token="t",
                                 transport=httpx.MockTransport(handler))
        assert await client.set_channel_status(5, CHANNEL_STATUS_ENABLED) is False

    @pytest.mark.asyncio
    async def test_list_channels_paginates(self):
        def handler(request: httpx.Request) -> httpx.Response:
            page = int(request.url.params.get("p", "1"))
            items = [{"id": i} for i in range(100)] if page == 1 else [{"id": 100}]
            return httpx.Response(200, json={"success": True, "data": {"items": items}})

        client = NewapiApiClient(base_url="http://newapi.test", token="t",
                                 transport=httpx.MockTransport(handler))
        channels = await client.list_channels()
        assert len(channels) == 101

    @pytest.mark.asyncio
    async def test_list_channels_network_error_returns_empty(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        client = NewapiApiClient(base_url="http://newapi.test", token="t",
                                 transport=httpx.MockTransport(handler))
        assert await client.list_channels() == []

    @pytest.mark.asyncio
    async def test_get_channel_contract(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/channel/7"
            return httpx.Response(200, json={"success": True, "data": {"id": 7, "status": 2}})

        client = NewapiApiClient(base_url="http://newapi.test", token="t",
                                 transport=httpx.MockTransport(handler))
        assert await client.get_channel(7) == {"id": 7, "status": 2}

    @pytest.mark.asyncio
    async def test_chat_completion_parses_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["model"] == "gpt-4o" and body["stream"] is False
            assert request.headers.get("Authorization") == "Bearer sk-probe"
            return httpx.Response(200, json={
                "model": "gpt-4o",
                "choices": [{"message": {"content": "我是 gpt-4o"}}],
                "usage": {"total_tokens": 42,
                          "completion_tokens_details": {"reasoning_tokens": 7}},
            })

        with patch.object(newapi_api_mod, "settings",
                          _fake_settings(**{"NEWAPI.PROBE_API_KEY": "sk-probe"})):
            client = NewapiApiClient(base_url="http://newapi.test", token="tok",
                                     transport=httpx.MockTransport(handler))
            r = await client.chat_completion("gpt-4o", "你是什么模型")
        assert r["ok"] is True
        assert r["content"] == "我是 gpt-4o"
        assert r["reasoning_tokens"] == 7
        assert r["usage"]["total_tokens"] == 42
        assert r["error"] is None

    @pytest.mark.asyncio
    async def test_chat_completion_http_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        client = NewapiApiClient(base_url="http://newapi.test", token="t",
                                 transport=httpx.MockTransport(handler))
        r = await client.chat_completion("gpt-4o", "你好")
        assert r["ok"] is False
        assert "500" in r["error"]
