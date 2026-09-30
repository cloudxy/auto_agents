"""注册邮箱验证（决策 D21 前置闸，2026-09-29）

免费档可用平台 LLM 做 AI 规划；为防批量注册薅额度，企业自助注册后负责人须验证邮箱：
- 验证链接带签名令牌（JWT typ=email_verify，AUTH.EMAIL_VERIFY_TTL_HOURS，默认 72 小时），
  指向后台 SITE.ADMIN_URL/verify-email；令牌与账号邮箱绑定，改过邮箱的旧链接失效
- 判定按企业：企业负责人仍待验证 → 整家企业不能用 AI 规划（负责人另建成员绕不过去）
- 重新发送每账号 60 秒一次（Redis；Redis 故障时放行——多发一封的代价远小于发不出去）
"""
from __future__ import annotations

import time
from typing import Any, Optional

import jwt
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.mail_service import send_mail
from backend.utils.auth import ALGORITHM, SECRET_KEY, decode_token_any
from config import settings
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger
from platform_core.models.user import User
from platform_core.redis_async import get_async_redis
from platform_core.timeutil import utcnow

logger = get_logger("service.email_verification")

EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"
_RESEND_KEY = "auth:verify-email:resend:{user_id}"
_RESEND_INTERVAL = 60


def _cfg(section: str, key: str, default: Any) -> Any:
    block = settings.get(section) or {}
    value = block.get(key, default) if hasattr(block, "get") else default
    return default if value in (None, "") else value


def make_token(user_id: int, email: str) -> str:
    logger.debug(f"生成邮箱验证令牌 | user_id={user_id}")
    now = int(time.time())
    ttl = int(_cfg("AUTH", "EMAIL_VERIFY_TTL_HOURS", 72)) * 3600
    return jwt.encode({"typ": "email_verify", "user_id": int(user_id), "email": email,
                       "iat": now, "exp": now + ttl}, SECRET_KEY, algorithm=ALGORITHM)


def verify_link(token: str) -> str:
    logger.debug("拼装邮箱验证链接")
    base = str(_cfg("SITE", "ADMIN_URL", "http://127.0.0.1:9112")).rstrip("/")
    return f"{base}/verify-email?token={token}"


async def send_verification(user_id: int, email: str) -> bool:
    """发验证邮件；失败只记日志（不挡注册主路径）"""
    logger.info(f"发送邮箱验证 | user_id={user_id}")
    link = verify_link(make_token(user_id, email))
    return await send_mail(
        email, "验证你的企业邮箱 · AutoAgents",
        "欢迎使用 AutoAgents。请点击下面的链接验证邮箱（72 小时内有效），验证后即可使用 AI 规划：\n\n"
        f"{link}\n\n如果不是你本人注册，请忽略这封邮件。",
    )


async def verify(session: AsyncSession, token: str) -> None:
    logger.info("校验邮箱验证令牌")
    payload = decode_token_any(token or "")
    if not payload or payload.get("typ") != "email_verify":
        raise BusinessException(message="验证链接无效或已过期，请在后台重新发送。", code="EMAIL_VERIFY_INVALID")
    user_id = int(payload.get("user_id") or 0)
    user = await session.get(User, user_id)
    if user is None or (user.email or "").lower() != str(payload.get("email") or "").lower():
        raise BusinessException(message="验证链接无效或已过期，请在后台重新发送。", code="EMAIL_VERIFY_INVALID")
    if user.email_verify_pending:
        user.email_verify_pending = False
        user.email_verified_at = utcnow()
        await session.commit()


async def resend(session: AsyncSession, user_id: int) -> None:
    """重新发送验证邮件（负责人本人；60 秒一次）"""
    logger.info(f"重发邮箱验证 | user_id={user_id}")
    user = await session.get(User, user_id)
    email = str(getattr(user, "email", "") or "")
    pending = bool(getattr(user, "email_verify_pending", False))
    if not pending:
        raise BusinessException(message="邮箱已验证，无需重新发送。", code="EMAIL_ALREADY_VERIFIED", status_code=409)
    try:
        allowed = await get_async_redis().set(_RESEND_KEY.format(user_id=user_id), "1", nx=True, ex=_RESEND_INTERVAL)
    except Exception as exc:  # noqa: BLE001 限频读写失败放行
        logger.warning(f"重发验证限频不可用，放行 | user_id={user_id} err={exc}")
        allowed = True
    if not allowed:
        raise BusinessException(message="发送太频繁，请 1 分钟后再试。", code="EMAIL_VERIFY_TOO_FREQUENT", status_code=429)
    await send_verification(user_id, email)


async def company_verify_pending(session: AsyncSession, tenant_id: Optional[int]) -> bool:
    """企业负责人是否仍待验证邮箱（按企业判定；无企业 = 平台账号，不适用）"""
    logger.debug(f"查询企业邮箱验证状态 | tenant={tenant_id}")
    if tenant_id is None:
        return False
    return bool((await session.execute(select(exists().where(
        User.tenant_id == tenant_id, User.tenant_role == "owner",
        User.email_verify_pending.is_(True), User.deleted_at.is_(None),
    )))).scalar())

