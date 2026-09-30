"""邮件发送（决策 D25：对外联系、到期提醒、注册邮箱验证都走邮箱）

- MAIL.ENABLED=false（开发 / 测试默认）：写进 MAIL.OUTBOX_DIR 下的 .eml 文件，流程照常走通，
  开发者打开文件即可拿到验证链接。
- MAIL.ENABLED=true：标准库 smtplib 发出（USE_SSL=true 走 465 SSL，否则 STARTTLS），在线程里
  执行不阻塞事件循环。账号口令只读环境变量 MAIL_USERNAME / MAIL_PASSWORD。
- 发送失败返回 False 并记日志，不抛到业务主路径（提醒 / 验证邮件失败不能让注册、巡检失败）。
"""
from __future__ import annotations

import asyncio
import os
import smtplib
import ssl
import time
import uuid
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Any

from config import settings
from platform_core.fs_guard import assert_contained
from platform_core.logger import get_logger

logger = get_logger("service.mail")

_ROOT = Path(__file__).resolve().parents[2]


def _cfg(key: str, default: Any) -> Any:
    section = settings.get("MAIL") or {}
    value = section.get(key, default) if hasattr(section, "get") else default
    return default if value is None else value


def _build(to: str, subject: str, text: str, html: str | None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = str(_cfg("FROM", "AutoAgents <no-reply@example.com>"))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain="autoagents.local")
    msg.set_content(text, charset="utf-8")
    if html:
        msg.add_alternative(html, subtype="html", charset="utf-8")
    return msg


def _write_outbox(msg: EmailMessage) -> None:
    outbox = Path(str(_cfg("OUTBOX_DIR", "runtime/mail_outbox")))
    if not outbox.is_absolute():
        outbox = _ROOT / outbox
    outbox.mkdir(parents=True, exist_ok=True)
    dest = assert_contained(outbox / f"{int(time.time())}-{uuid.uuid4().hex[:8]}.eml", outbox)
    dest.write_bytes(bytes(msg))
    logger.info(f"邮件未启用 SMTP，已写入发件箱 | to={msg['To']} file={dest.name}")


def _smtp_send(msg: EmailMessage) -> None:
    host = str(_cfg("HOST", "") or "")
    port = int(_cfg("PORT", 465))
    timeout = float(_cfg("TIMEOUT_SECONDS", 10))
    user = os.getenv("MAIL_USERNAME") or ""
    password = os.getenv("MAIL_PASSWORD") or ""
    if bool(_cfg("USE_SSL", True)):
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context()) as smtp:
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
        return
    with smtplib.SMTP(host, port, timeout=timeout) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        if user:
            smtp.login(user, password)
        smtp.send_message(msg)


async def send_mail(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """发一封邮件；成功（或已写入本地发件箱）返回 True，失败返回 False"""
    logger.info(f"发送邮件 | to={to} subject={subject}")
    msg = _build(to, subject, text, html)
    try:
        if not bool(_cfg("ENABLED", False)):
            _write_outbox(msg)
            return True
        await asyncio.to_thread(_smtp_send, msg)
        logger.info(f"邮件已发出 | to={to}")
        return True
    except Exception as exc:  # noqa: BLE001 邮件失败不挡业务主路径
        logger.error(f"邮件发送失败 | to={to} err={type(exc).__name__}: {exc}")
        return False
