"""限流深模块（B1，工单 74-76）——公开面防护一处声明

设计（对齐 check-arch 文化：策略数据类 + 无状态引擎）：
- RateLimitPolicy：键前缀/窗口/阈值/失败方向/XFF 策略 一处声明
- 引擎函数显式接收 redis 句柄（调用方注入，便于测试替换与复用连接）
- 失败方向：
  - fail_open=True：Redis 故障时放行（可用性优先：登录/注册/公开只读面）
  - fail_open=False：Redis 故障时拒绝（反滥用优先：无鉴权写面，如租户自助注册）
- XFF 策略：
  - "none"：直连语义，取 request.client.host
  - "last"：取 X-Forwarded-For 最右值（由本层可信反代写入；首跳可伪造，禁用）

键契约（platform_core/queues.py）：LOGIN_FAIL_PREFIX / REGISTER_ATTEMPT_PREFIX /
SIGNUP_RATE_PREFIX / SKILL_PUBLIC_RATE_PREFIX。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from fastapi import Request
from redis.exceptions import RedisError

from platform_core.exceptions import RateLimitException
from platform_core.logger import get_logger
from platform_core.queues import (
    LOGIN_FAIL_PREFIX,
    REGISTER_ATTEMPT_PREFIX,
    SIGNUP_RATE_PREFIX,
    SKILL_PUBLIC_RATE_PREFIX,
)

logger = get_logger("api.ratelimit")

XffMode = Literal["none", "last"]


@dataclass(frozen=True)
class RateLimitPolicy:
    """限流策略声明（一处定义，全端点复用）"""

    name: str                 # 策略名（日志定位）
    key_prefix: str           # Redis 键前缀（契约见 queues.py）
    window_seconds: int       # 计数窗口
    max_requests: int         # 窗口内最大次数
    fail_open: bool           # Redis 故障方向：True 放行 / False 拒绝
    xff_mode: XffMode = "none"


# ── 平台策略注册表（新公开端点从此取策略，一行获得限流）──

LOGIN_FAIL_POLICY = RateLimitPolicy(
    name="login_fail", key_prefix=LOGIN_FAIL_PREFIX,
    window_seconds=900, max_requests=5, fail_open=True,
)

REGISTER_ATTEMPT_POLICY = RateLimitPolicy(
    name="register_attempt", key_prefix=REGISTER_ATTEMPT_PREFIX,
    window_seconds=900, max_requests=5, fail_open=True,
)

# 无鉴权写面（租户自助注册）：反滥用优先，fail-closed
SIGNUP_RATE_POLICY = RateLimitPolicy(
    name="tenant_signup", key_prefix=SIGNUP_RATE_PREFIX,
    window_seconds=900, max_requests=5, fail_open=False, xff_mode="last",
)

SKILL_PUBLIC_RATE_POLICY = RateLimitPolicy(
    name="skill_public", key_prefix=SKILL_PUBLIC_RATE_PREFIX,
    window_seconds=60, max_requests=60, fail_open=True, xff_mode="last",
)


def resolve_client_ip(request: Request, xff_mode: XffMode = "none") -> str:
    """按策略取客户端 IP（XFF 首跳客户端可伪造，仅允许取最右可信反代值）"""
    if xff_mode == "last":
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def policy_key(policy: RateLimitPolicy, identity: str) -> str:
    return f"{policy.key_prefix}{identity}"


async def check_rate_limit(redis, policy: RateLimitPolicy, identity: str) -> None:
    """检查窗口计数是否已达阈值（达阈值抛 RateLimitException，retry_after=剩余 TTL）

    只读检查不计数；计数由 record_attempt / hit 完成（登录场景只计失败，
    注册/公开面场景成功失败均计）。
    """
    key = policy_key(policy, identity)
    try:
        count = await redis.get(key)
        if count and int(count) >= policy.max_requests:
            ttl = await redis.ttl(key)
            minutes = max(1, -(-max(ttl, 0) // 60))  # 向上取整，ttl 异常时保守 1 分钟
            raise RateLimitException(
                message=f"{policy.name} 请求过于频繁，请{minutes}分钟后再试",
                retry_after=max(ttl, 60),
            )
    except RateLimitException:
        raise
    except RedisError:
        _on_redis_failure(policy, key, "check")


async def record_attempt(redis, policy: RateLimitPolicy, identity: str) -> None:
    """记录一次请求/失败（pipeline INCR+EXPIRE 原子提交，杜绝无 TTL 永久计数器）"""
    key = policy_key(policy, identity)
    try:
        pipe = redis.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, policy.window_seconds)
        await pipe.execute()
    except RedisError:
        _on_redis_failure(policy, key, "record")


async def hit_rate_limit(redis, policy: RateLimitPolicy, identity: str) -> None:
    """计数 + 检查一体（固定窗口；注册/公开面场景：成功失败均计数）"""
    key = policy_key(policy, identity)
    try:
        pipe = redis.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, policy.window_seconds)
        count, _ = await pipe.execute()
        if int(count) > policy.max_requests:
            ttl = await redis.ttl(key)
            raise RateLimitException(
                message=f"请求过于频繁（限 {policy.max_requests} 次/"
                        f"{policy.window_seconds // 60} 分钟），请稍后再试",
                retry_after=max(ttl, 60),
            )
    except RateLimitException:
        raise
    except RedisError:
        _on_redis_failure(policy, key, "hit")


async def enforce_request_limit(
    redis, policy: RateLimitPolicy, request: Request,
    *, identity: Optional[str] = None,
) -> None:
    """端点便捷入口：identity 优先（用户名等业务维度），否则按 XFF 策略取 IP"""
    ident = identity or resolve_client_ip(request, policy.xff_mode)
    await hit_rate_limit(redis, policy, ident)


def _on_redis_failure(policy: RateLimitPolicy, key: str, phase: str) -> None:
    """Redis 故障的失败方向处置（fail-open 放行 / fail-closed 拒绝）"""
    if policy.fail_open:
        logger.warning(f"限流检查失败，fail-open 放行 | policy={policy.name} key={key} phase={phase}")
        return
    logger.warning(f"限流服务故障，fail-closed 拒绝 | policy={policy.name} key={key} phase={phase}")
    raise RateLimitException(message="服务暂时不可用，请稍后再试", retry_after=30)
