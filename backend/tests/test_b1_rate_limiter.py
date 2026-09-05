"""B1 公开面防护收口（工单 74-76）：限流深模块 + signup Pydantic + 密钥 fail-fast

期望值全部来自独立事实源（策略表常量、字面量）。
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
import redis.exceptions
from fastapi import Request
from loguru import logger as _loguru

from backend.app.api.v1.tenant_signup import TenantSignupRequest
from backend.app.core.rate_limiter import (
    LOGIN_FAIL_POLICY,
    SIGNUP_RATE_POLICY,
    SKILL_PUBLIC_RATE_POLICY,
    check_rate_limit,
    hit_rate_limit,
    resolve_client_ip,
)
from platform_core.exceptions import RateLimitException

_REDIS_DOWN = redis.exceptions.ConnectionError("redis down")


def _redis(count: int | None = None, ttl: int = 300):
    m = MagicMock()
    m.get = AsyncMock(return_value=str(count).encode() if count is not None else None)
    m.ttl = AsyncMock(return_value=ttl)
    pipe = MagicMock()
    pipe.incr = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[1, True])
    m.pipeline = MagicMock(return_value=pipe)
    return m


# ---------------- 策略表（一处声明的事实源）----------------

def test_policy_table_directions():
    """失败方向声明：无鉴权写面 fail-closed，其余 fail-open"""
    assert LOGIN_FAIL_POLICY.fail_open is True          # 登录（可用性）
    assert SKILL_PUBLIC_RATE_POLICY.fail_open is True   # 公开只读（可用性）
    assert SIGNUP_RATE_POLICY.fail_open is False        # 租户注册写面（反滥用）
    # XFF 策略：公开面取最右可信值
    assert SIGNUP_RATE_POLICY.xff_mode == "last"
    assert SKILL_PUBLIC_RATE_POLICY.xff_mode == "last"
    assert LOGIN_FAIL_POLICY.xff_mode == "none"         # 用户名维度，不涉 IP


# ---------------- XFF 取最右（首跳可伪造，弃用）----------------

def _req(xff: str | None, host: str = "10.0.0.1") -> Request:
    r = MagicMock(spec=Request)
    r.headers = {"x-forwarded-for": xff} if xff else {}
    r.client = MagicMock()
    r.client.host = host
    return r


def test_xff_takes_rightmost_trusted_value():
    """伪造首跳不生效：取最右（本层反代写入值）"""
    ip = resolve_client_ip(_req("1.2.3.4, 5.6.7.8"), "last")
    assert ip == "5.6.7.8"
    assert resolve_client_ip(_req("1.2.3.4"), "none") == "10.0.0.1"
    assert resolve_client_ip(_req(None), "last") == "10.0.0.1"


# ---------------- fail-closed：Redis 故障拒绝 ----------------

@pytest.mark.asyncio
async def test_fail_closed_signup_rejects_on_redis_failure():
    m = _redis()
    m.pipeline.return_value.execute = AsyncMock(side_effect=_REDIS_DOWN)
    with pytest.raises(RateLimitException):
        await hit_rate_limit(m, SIGNUP_RATE_POLICY, "1.2.3.4")


@pytest.mark.asyncio
async def test_fail_open_login_passes_on_redis_failure(monkeypatch):
    m = _redis()
    m.get = AsyncMock(side_effect=_REDIS_DOWN)
    records: list[str] = []
    sink = _loguru.add(lambda msg: records.append(str(msg)), level="WARNING", catch=True)
    try:
        await check_rate_limit(m, LOGIN_FAIL_POLICY, "alice")  # 不抛即 fail-open 生效
    finally:
        _loguru.remove(sink)
    assert any("login_fail:alice" in r for r in records)


# ---------------- 阈值语义 ----------------

@pytest.mark.asyncio
async def test_check_raises_at_threshold():
    m = _redis(count=LOGIN_FAIL_POLICY.max_requests, ttl=600)
    with pytest.raises(RateLimitException):
        await check_rate_limit(m, LOGIN_FAIL_POLICY, "bob")


@pytest.mark.asyncio
async def test_hit_increments_and_rejects_over_limit():
    m = _redis()
    m.pipeline.return_value.execute = AsyncMock(
        return_value=[SIGNUP_RATE_POLICY.max_requests + 1, True])
    with pytest.raises(RateLimitException):
        await hit_rate_limit(m, SIGNUP_RATE_POLICY, "1.2.3.4")


# ---------------- signup Pydantic（替代裸 dict）----------------

def test_signup_request_rejects_short_password():
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        TenantSignupRequest(company="某公司", admin_email="a@b.co", admin_password="short")


def test_signup_request_rejects_bad_email():
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        TenantSignupRequest(company="某公司", admin_email="not-an-email", admin_password="longenough1")


def test_signup_request_normalizes_email():
    r = TenantSignupRequest(company="某公司", admin_email="  A@B.CO ", admin_password="longenough1")
    assert r.admin_email == "a@b.co"


# ---------------- LLM_ENCRYPTION_KEY 占位符 fail-fast ----------------

def test_llm_key_placeholder_rejects_startup(monkeypatch):
    from backend.app import _validate_runtime_secrets
    monkeypatch.setenv("LLM_ENCRYPTION_KEY", "change-me-in-production")
    monkeypatch.setattr(
        "backend.app.settings",
        MagicMock(**{"get": lambda k, d=None: "set" if k == "WEBHOOK.SECRET_KEY" else ""}),
    )
    with pytest.raises(RuntimeError, match="LLM_ENCRYPTION_KEY"):
        _validate_runtime_secrets()


def test_llm_key_invalid_fernet_rejects_startup(monkeypatch):
    from backend.app import _validate_runtime_secrets
    monkeypatch.setenv("LLM_ENCRYPTION_KEY", "not-a-fernet-key!!")
    monkeypatch.setattr(
        "backend.app.settings",
        MagicMock(**{"get": lambda k, d=None: "set" if k == "WEBHOOK.SECRET_KEY" else ""}),
    )
    with pytest.raises(RuntimeError, match="Fernet"):
        _validate_runtime_secrets()


def test_llm_key_empty_allows_fallback_mode(monkeypatch):
    """空密钥 = yml/env 兜底模式，不阻断启动"""
    from backend.app import _validate_runtime_secrets
    monkeypatch.delenv("LLM_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(
        "backend.app.settings",
        MagicMock(**{"get": lambda k, d=None: "set" if k == "WEBHOOK.SECRET_KEY" else ""}),
    )
    _validate_runtime_secrets()  # 不抛即通过
