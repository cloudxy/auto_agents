"""会话续期（决策 D10 = A，2026-09-29）

原状：访问令牌 30 分钟、没有 refresh，客户每干 30 分钟活就被踢回登录页。

- 登录下发一对令牌：访问令牌（JWT.ACCESS_TOKEN_EXPIRE_MINUTES，默认 30 分钟）+ 刷新令牌
  （勾「记住我」JWT.REFRESH_TOKEN_EXPIRE_DAYS 天，不勾 JWT.SESSION_REFRESH_HOURS 小时）。
- 刷新即轮换：每个刷新令牌只换一次。Redis 记已用 jti（TTL = 剩余寿命）；同一令牌在
  JWT.REFRESH_REUSE_GRACE_SECONDS 秒内再换（多标签页并发）照常放行，超出宽限再出现 =
  疑似被盗 → token_version +1，吊销该用户全部会话。
- 会话从首次登录起算绝对上限 JWT.SESSION_MAX_DAYS 天，轮换不续命。
- 每次刷新都按库重核：停用、改密（token_version）、企业停用 → 拒绝。
- Redis 不可用时刷新失败（fail-closed：重新登录，不放宽）。
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Optional

import jwt
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.utils.auth import ALGORITHM, SECRET_KEY, create_access_token, decode_token_any
from config import settings
from platform_core.exceptions import AuthenticationException
from platform_core.logger import get_logger
from platform_core.redis_async import get_async_redis

logger = get_logger("service.session")

_USED_KEY = "auth:refresh:used:{jti}"
_LOGGED_OUT = "logged-out"


def _jwt_cfg(key: str, default: Any) -> Any:
    section = settings.get("JWT") or {}
    value = section.get(key, default) if hasattr(section, "get") else default
    return default if value in (None, "") else value


def _now_ts() -> float:
    return time.time()


def access_ttl_seconds() -> int:
    logger.debug("读取访问令牌有效期")
    return int(_jwt_cfg("ACCESS_TOKEN_EXPIRE_MINUTES", 30)) * 60


def _refresh_ttl_seconds(remember: bool) -> int:
    if remember:
        return int(_jwt_cfg("REFRESH_TOKEN_EXPIRE_DAYS", 7)) * 86400
    return int(_jwt_cfg("SESSION_REFRESH_HOURS", 12)) * 3600


def access_claims(user: dict) -> dict:
    """访问令牌只承身份（S1-3）；权限一律按库快照重算"""
    logger.debug(f"组装访问令牌 claims | user_id={user.get('id')}")
    return {
        "sub": user["username"],
        "user_id": user["id"],
        "role": user.get("role", "operator"),
        "tenant_id": user.get("tenant_id"),
        "tenant_role": user.get("tenant_role"),
        "is_platform_admin": bool(user.get("is_platform_admin", False)),
        "tv": int(user.get("token_version", 0) or 0),
    }


def issue_session(user: dict, *, remember: bool, auth_time: Optional[int] = None) -> dict:
    """签发访问 + 刷新令牌对"""
    logger.info(f"签发会话 | user_id={user.get('id')} remember={remember}")
    now = int(_now_ts())
    refresh = jwt.encode({
        "typ": "refresh",
        "sub": user["username"],
        "user_id": user["id"],
        "tv": int(user.get("token_version", 0) or 0),
        "jti": uuid.uuid4().hex,
        "rm": bool(remember),
        "at": int(auth_time or now),
        "iat": now,
        "exp": now + _refresh_ttl_seconds(remember),
    }, SECRET_KEY, algorithm=ALGORITHM)
    return {
        "access_token": create_access_token(access_claims(user)),
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": access_ttl_seconds(),
    }


def _decode_refresh(token: str, verify_exp: bool = True) -> Optional[dict]:
    payload = decode_token_any(token, verify_exp=verify_exp)
    if not payload or payload.get("typ") != "refresh" or not payload.get("jti"):
        return None
    return payload


async def _revoke_all(session: AsyncSession, user_id: int) -> None:
    from platform_core.models.user import User

    logger.warning(f"刷新令牌被重复使用，吊销该用户全部会话 | user_id={user_id}")
    await session.execute(
        update(User).where(User.id == user_id).values(token_version=User.token_version + 1)
    )
    await session.commit()


async def rotate(session: AsyncSession, refresh_token: str) -> dict:
    """用刷新令牌换一对新令牌（轮换）；任何不满足都抛 401"""
    logger.info("刷新会话")
    from backend.services.tenant_expiry_service import assert_tenant_active
    from backend.services.user_service import load_auth_identity, token_version_matches

    payload = _decode_refresh(refresh_token)
    if payload is None:
        raise AuthenticationException(message="登录已过期，请重新登录")
    user_id = int(payload["user_id"])
    now = _now_ts()
    max_age = int(_jwt_cfg("SESSION_MAX_DAYS", 30)) * 86400
    if now - float(payload.get("at") or payload.get("iat") or 0) > max_age:
        raise AuthenticationException(message="登录已过期，请重新登录")

    key = _USED_KEY.format(jti=payload["jti"])
    try:
        redis = get_async_redis()
        ttl = max(1, int(float(payload["exp"]) - now))
        first_use = await redis.set(key, str(now), nx=True, ex=ttl)
        used_at = None if first_use else await redis.get(key)
    except Exception as exc:  # noqa: BLE001 fail-closed：宁可重新登录，不放过重放
        logger.error(f"刷新会话读写 Redis 失败 | user_id={user_id} err={exc}")
        raise AuthenticationException(message="登录已过期，请重新登录") from exc
    if not first_use:
        if used_at in (_LOGGED_OUT, _LOGGED_OUT.encode()):
            # 本会话已登出：只拒这一张，不株连其它设备
            raise AuthenticationException(message="登录已过期，请重新登录")
        grace = float(_jwt_cfg("REFRESH_REUSE_GRACE_SECONDS", 30))
        if used_at is None or now - float(used_at) > grace:
            await _revoke_all(session, user_id)
            raise AuthenticationException(message="登录已失效，请重新登录")

    identity = await load_auth_identity(session, user_id)
    if identity is None or not identity.is_active:
        raise AuthenticationException(message="用户不存在或已停用")
    if not token_version_matches(payload, identity):
        raise AuthenticationException(message="登录已失效，请重新登录")
    await assert_tenant_active(session, identity.tenant_id, is_platform_admin=identity.is_platform_admin)
    user = {
        "id": identity.id, "username": identity.username, "role": identity.role,
        "tenant_id": identity.tenant_id, "tenant_role": identity.tenant_role,
        "is_platform_admin": identity.is_platform_admin, "token_version": identity.token_version,
    }
    return issue_session(user, remember=bool(payload.get("rm")), auth_time=int(payload.get("at") or now))


async def revoke(refresh_token: Optional[str]) -> None:
    """登出：作废本会话的刷新令牌（其它设备不受影响）；令牌无效时静默"""
    logger.info("登出会话")
    payload = _decode_refresh(refresh_token or "", verify_exp=False)
    if payload is None:
        return
    ttl = max(1, int(float(payload["exp"]) - _now_ts()))
    try:
        await get_async_redis().set(_USED_KEY.format(jti=payload["jti"]), _LOGGED_OUT, ex=ttl)
    except Exception as exc:  # noqa: BLE001 登出不因 Redis 故障报错；访问令牌照常到期
        logger.warning(f"登出时作废刷新令牌失败 | err={exc}")
