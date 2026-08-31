"""auth 限流原子化 + fail-open 显式化回归（任务 #35）

覆盖：
- record_login_failure：INCR+EXPIRE 走 pipeline 原子提交（与 record_register_attempt
  同构），不再裸 incr+expire 两次独立往返（两步间进程崩溃会残留无 TTL 永久
  计数器 → 用户名被永久 429）
- fail-open：Redis 故障（RedisError）时 login/register 的限流检查放行、计数
  跳过，主流程不 500；且只捕获 RedisError，其他异常照常冒泡
- 回归：正常 Redis 下达阈值仍 429（不吞限流），键名 / 窗口 TTL 语义不变
- 可观测：fail-open 路径 warning 日志包含限流键上下文
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
import redis.exceptions
from loguru import logger as _loguru

from backend.app.api.v1.auth import (
    check_login_rate_limit,
    record_login_failure,
    record_register_attempt,
)

_LOGIN_KEY = "login_fail:alice"
_LOGIN_FAIL_REDIS = redis.exceptions.ConnectionError("redis down")

LOGIN_BODY = {"username": "alice", "password": "pw-123456"}
REGISTER_BODY = {"username": "newuser", "email": "newuser@example.com", "password": "secret-123"}


def _redis_with_pipeline(execute_error: Exception | None = None):
    """构造带 pipeline 桩的 mock redis；execute_error 注入 pipeline 提交故障"""
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.ttl = AsyncMock(return_value=600)
    # 裸 incr/expire 不应再被调用（防止退回两次独立往返的旧实现）
    mock_redis.incr = AsyncMock()
    mock_redis.expire = AsyncMock()

    pipe = MagicMock()
    pipe.incr = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(
        return_value=[1, True] if execute_error is None else None,
        side_effect=execute_error,
    )
    mock_redis.pipeline = MagicMock(return_value=pipe)
    return mock_redis, pipe


def _patch_auth_redis(monkeypatch, mock_redis):
    monkeypatch.setattr(
        "backend.app.api.v1.auth.get_async_redis", lambda *a, **k: mock_redis
    )


class _FakeAuthService:
    """不触 DB 的 AuthService 桩（authenticate 结果由用例注入）"""

    authenticate_result = None  # None = 认证失败路径

    def __init__(self, db):
        pass

    async def authenticate(self, username, password):
        return self.authenticate_result

    async def create_token(self, user_data):
        return MagicMock(
            access_token="fake-token", token_type="bearer", username=user_data["username"]
        )

    async def register_user(self, **kwargs):
        return {"id": 99}


# ---------------- A：record_login_failure pipeline 原子化 ----------------
class TestRecordLoginFailurePipeline:
    """login 失败计数与 register 同构：pipeline(transaction=True) 同批提交"""

    @pytest.mark.asyncio
    async def test_uses_atomic_pipeline_incr_expire(self, monkeypatch):
        mock_redis, pipe = _redis_with_pipeline()
        _patch_auth_redis(monkeypatch, mock_redis)

        await record_login_failure("alice")

        mock_redis.pipeline.assert_called_once_with(transaction=True)
        pipe.incr.assert_called_once_with("login_fail:alice")
        pipe.expire.assert_called_once_with("login_fail:alice", 900)
        pipe.execute.assert_awaited_once()
        # 旧实现回归防护：不允许裸 incr / expire 直调（两次独立往返）
        mock_redis.incr.assert_not_awaited()
        mock_redis.expire.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_redis_error_skips_counter_without_raising(self, monkeypatch):
        """fail-open：pipeline 提交遇 RedisError 跳过计数，不向调用方抛 500"""
        mock_redis, _pipe = _redis_with_pipeline(
            execute_error=redis.exceptions.ConnectionError("redis down")
        )
        _patch_auth_redis(monkeypatch, mock_redis)

        await record_login_failure("alice")  # 不抛即通过


# ---------------- B：fail-open warning 日志含限流键上下文 ----------------
class TestFailOpenWarningLogContext:
    """fail-open 路径必须留 warning 痕迹且可定位到限流键（静默放行不可排查）"""

    @staticmethod
    def _capture_warnings():
        records: list[str] = []
        sink_id = _loguru.add(
            lambda msg: records.append(str(msg)), level="WARNING", catch=True
        )
        return records, sink_id

    @pytest.mark.asyncio
    async def test_login_check_warning_contains_key(self, monkeypatch):
        mock_redis, _pipe = _redis_with_pipeline()
        mock_redis.get = AsyncMock(side_effect=_LOGIN_FAIL_REDIS)
        _patch_auth_redis(monkeypatch, mock_redis)

        records, sink_id = self._capture_warnings()
        try:
            await check_login_rate_limit("alice")
        finally:
            _loguru.remove(sink_id)

        assert any(_LOGIN_KEY in r for r in records)

    @pytest.mark.asyncio
    async def test_login_record_warning_contains_key(self, monkeypatch):
        mock_redis, _pipe = _redis_with_pipeline(execute_error=_LOGIN_FAIL_REDIS)
        _patch_auth_redis(monkeypatch, mock_redis)

        records, sink_id = self._capture_warnings()
        try:
            await record_login_failure("alice")
        finally:
            _loguru.remove(sink_id)

        assert any(_LOGIN_KEY in r for r in records)

    @pytest.mark.asyncio
    async def test_register_record_warning_contains_key(self, monkeypatch):
        mock_redis, _pipe = _redis_with_pipeline(execute_error=_LOGIN_FAIL_REDIS)
        _patch_auth_redis(monkeypatch, mock_redis)

        records, sink_id = self._capture_warnings()
        try:
            await record_register_attempt("10.0.0.8")
        finally:
            _loguru.remove(sink_id)

        assert any("register_fail:10.0.0.8" in r for r in records)


# ---------------- B：fail-open 显式化（检查读路径 + 异常边界） ----------------
class TestRateLimitCheckFailOpen:
    """限流检查 Redis 故障放行；RateLimitException 不被误吞"""

    @pytest.mark.asyncio
    async def test_login_check_redis_error_fail_open(self, monkeypatch):
        mock_redis, _pipe = _redis_with_pipeline()
        mock_redis.get = AsyncMock(
            side_effect=redis.exceptions.ConnectionError("redis down")
        )
        _patch_auth_redis(monkeypatch, mock_redis)

        await check_login_rate_limit("alice")  # 不抛即放行

    @pytest.mark.asyncio
    async def test_login_check_still_blocks_at_threshold(self, monkeypatch):
        """fail-open 不吞限流：正常 Redis 下达阈值仍抛 RateLimitException"""
        mock_redis, _pipe = _redis_with_pipeline()
        mock_redis.get = AsyncMock(return_value="5")
        _patch_auth_redis(monkeypatch, mock_redis)

        from platform_core.exceptions import RateLimitException

        with pytest.raises(RateLimitException):
            await check_login_rate_limit("alice")

    @pytest.mark.asyncio
    async def test_only_redis_error_is_swallowed(self, monkeypatch):
        """只捕获 RedisError：其他异常（如数据类型问题）照常冒泡"""
        mock_redis, _pipe = _redis_with_pipeline()
        mock_redis.get = AsyncMock(return_value="not-a-number")
        _patch_auth_redis(monkeypatch, mock_redis)

        with pytest.raises(ValueError):
            await check_login_rate_limit("alice")

    @pytest.mark.asyncio
    async def test_register_record_redis_error_skips_counter(self, monkeypatch):
        mock_redis, _pipe = _redis_with_pipeline(
            execute_error=redis.exceptions.TimeoutError("redis timeout")
        )
        _patch_auth_redis(monkeypatch, mock_redis)

        await record_register_attempt("10.0.0.8")  # 不抛即通过


# ---------------- B：端到端 fail-open（HTTP 级，Redis 故障不 500） ----------------
class TestFailOpenEndToEnd:
    """Redis 故障时 login / register 走正常业务流程（200/401），而非 500"""

    def test_login_succeeds_when_check_redis_down(self, client, monkeypatch):
        mock_redis, _pipe = _redis_with_pipeline()
        mock_redis.get = AsyncMock(
            side_effect=redis.exceptions.ConnectionError("redis down")
        )
        _patch_auth_redis(monkeypatch, mock_redis)
        monkeypatch.setattr("backend.app.api.v1.auth.AuthService", _FakeAuthService)
        _FakeAuthService.authenticate_result = {"id": 1, "username": "alice", "role": "admin"}
        try:
            resp = client.post("/api/v1/auth/login", json=LOGIN_BODY)
        finally:
            _FakeAuthService.authenticate_result = None

        assert resp.status_code == 200
        assert resp.json()["data"]["access_token"] == "fake-token"

    def test_login_failure_still_401_when_record_redis_down(self, client, monkeypatch):
        """认证失败路径：计数写入故障被吞后仍返回 401（而非 500）"""
        mock_redis, _pipe = _redis_with_pipeline(
            execute_error=redis.exceptions.ConnectionError("redis down")
        )
        _patch_auth_redis(monkeypatch, mock_redis)

        class _FailedAuthService(_FakeAuthService):
            async def authenticate(self, username, password):
                return None  # 密码错误

        monkeypatch.setattr("backend.app.api.v1.auth.AuthService", _FailedAuthService)

        resp = client.post("/api/v1/auth/login", json=LOGIN_BODY)

        assert resp.status_code == 401
        assert resp.json()["code"] == "AUTH_FAILED"

    def test_register_succeeds_when_check_redis_down(self, client, monkeypatch):
        mock_redis, _pipe = _redis_with_pipeline()
        mock_redis.get = AsyncMock(
            side_effect=redis.exceptions.ConnectionError("redis down")
        )
        _patch_auth_redis(monkeypatch, mock_redis)
        monkeypatch.setattr("backend.app.api.v1.auth.AuthService", _FakeAuthService)

        resp = client.post("/api/v1/auth/register", json=REGISTER_BODY)

        assert resp.status_code == 200
        assert resp.json()["data"]["user_id"] == 99

    def test_register_succeeds_when_record_redis_down(self, client, monkeypatch):
        mock_redis, _pipe = _redis_with_pipeline(
            execute_error=redis.exceptions.ConnectionError("redis down")
        )
        _patch_auth_redis(monkeypatch, mock_redis)
        monkeypatch.setattr("backend.app.api.v1.auth.AuthService", _FakeAuthService)

        resp = client.post("/api/v1/auth/register", json=REGISTER_BODY)

        assert resp.status_code == 200

    def test_register_still_blocked_at_threshold(self, client, monkeypatch):
        """fail-open 回归防护：正常 Redis 下达阈值仍 429（计数不递增）"""
        mock_redis, pipe = _redis_with_pipeline()
        mock_redis.get = AsyncMock(return_value="5")
        _patch_auth_redis(monkeypatch, mock_redis)

        resp = client.post("/api/v1/auth/register", json=REGISTER_BODY)

        assert resp.status_code == 429
        assert resp.json()["code"] == "RATE_LIMITED"
        pipe.incr.assert_not_called()  # check 先于 record：阻断后不再计数
