"""任务终态告警通知服务

职责：
- 任务推进到终态（completed/failed）后，按 NOTIFY.CHANNELS 配置分发通知
- 渠道：log（兜底日志）/ webhook（POST JSON）/ email（SMTP，aiosmtplib）/
  dingtalk（群机器人，可选 HmacSHA256 加签）/ wechat_work（企业微信机器人，markdown）

约束：
- 通知失败仅记日志，绝不向上抛异常（不影响任务主流程）；渠道互不影响
- 渠道与目标地址全部来自配置（config/default/notify.yml，可被 .env 覆盖）
"""
import base64
import hashlib
import hmac
import time
import urllib.parse
from email.message import EmailMessage
from typing import Optional

import aiosmtplib
import httpx

from config import settings
from platform_core.logger import get_logger

logger = get_logger("api")


def _render_text(payload: dict) -> str:
    """通知文案统一渲染（email/dingtalk/wechat_work 渠道共用）"""
    status_label = "失败" if payload["status"] == "failed" else "完成"
    lines = [
        f"【爬虫平台】任务 #{payload['task_id']} 已{status_label}",
        f"爬虫: {payload['spider_name']}",
        f"状态: {payload['status']}",
        f"采集结果: {payload['result_count']} 条",
        f"重试次数: {payload['retry_count']}",
    ]
    if payload["error_message"]:
        lines.append(f"错误信息: {payload['error_message']}")
    return "\n".join(lines)


class NotifyService:
    """任务终态通知分发"""

    def __init__(self):
        self._enabled: bool = bool(settings.get("NOTIFY.ENABLED", True))
        channels = settings.get("NOTIFY.CHANNELS", ["log"])
        self._channels = list(channels) if channels else ["log"]
        self._webhook_url: str = str(settings.get("NOTIFY.WEBHOOK_URL", "") or "")
        self._timeout: float = float(settings.get("NOTIFY.TIMEOUT_SECONDS", 10))
        # 阶段 4.3 新增渠道配置（缺失时对应渠道自动跳过）
        self._email_host: str = str(settings.get("NOTIFY.EMAIL.SMTP_HOST", "") or "")
        self._email_port: int = int(settings.get("NOTIFY.EMAIL.SMTP_PORT", 465))
        self._email_user: str = str(settings.get("NOTIFY.EMAIL.SMTP_USER", "") or "")
        self._email_password: str = str(settings.get("NOTIFY.EMAIL.SMTP_PASSWORD", "") or "")
        self._email_ssl: bool = bool(settings.get("NOTIFY.EMAIL.SMTP_SSL", True))
        self._email_from: str = str(settings.get("NOTIFY.EMAIL.MAIL_FROM", "") or "")
        mail_to = settings.get("NOTIFY.EMAIL.MAIL_TO", []) or []
        self._email_to: list[str] = [mail_to] if isinstance(mail_to, str) else list(mail_to)
        self._dingtalk_url: str = str(settings.get("NOTIFY.DINGTALK.WEBHOOK_URL", "") or "")
        self._dingtalk_secret: str = str(settings.get("NOTIFY.DINGTALK.SECRET", "") or "")
        self._wechat_url: str = str(settings.get("NOTIFY.WECHAT_WORK.WEBHOOK_URL", "") or "")

    async def notify_task_finished(
        self,
        task_id: int,
        spider_name: str,
        status: str,
        result_count: int = 0,
        retry_count: int = 0,
        error_message: Optional[str] = None,
    ) -> None:
        """任务终态通知入口（吞掉所有异常）"""
        if not self._enabled:
            return
        payload = {
            "event": "task.finished",
            "task_id": task_id,
            "spider_name": spider_name,
            "status": status,
            "result_count": result_count,
            "retry_count": retry_count,
            "error_message": error_message,
        }
        for channel in self._channels:
            try:
                if channel == "log":
                    self._notify_log(payload)
                elif channel == "webhook":
                    await self._notify_webhook(payload)
                elif channel == "email":
                    await self._notify_email(payload)
                elif channel == "dingtalk":
                    await self._notify_dingtalk(payload)
                elif channel == "wechat_work":
                    await self._notify_wechat_work(payload)
                else:
                    logger.warning(f"未知通知渠道，已跳过: channel={channel}")
            except Exception as e:  # noqa: BLE001 通知失败不影响主流程
                logger.error(f"通知渠道执行失败: channel={channel}, task_id={task_id}, error={e}")

    async def notify_text(self, event: str, text: str) -> None:
        """通用文本通知（渠道调度器/探针等后台事件复用通知栈；吞掉所有异常）

        与 notify_task_finished 共享渠道配置（NOTIFY.CHANNELS/WEBHOOK_URL/EMAIL/DINGTALK/
        WECHAT_WORK），但载荷为通用 {event, text}，不复用任务终态文案渲染。
        """
        if not self._enabled:
            return
        full = f"[{event}] {text}"
        for channel in self._channels:
            try:
                if channel == "log":
                    logger.info(full)
                elif channel == "webhook" and self._webhook_url:
                    async with httpx.AsyncClient(trust_env=False, timeout=self._timeout) as client:
                        resp = await client.post(
                            self._webhook_url, json={"event": event, "text": text}
                        )
                        if resp.status_code >= 400:
                            logger.warning(
                                f"webhook 通知返回异常状态: event={event}, http={resp.status_code}"
                            )
                elif channel == "dingtalk" and self._dingtalk_url:
                    async with httpx.AsyncClient(trust_env=False, timeout=self._timeout) as client:
                        await client.post(
                            self._dingtalk_url, json={"msgtype": "text", "text": {"content": full}}
                        )
                elif channel == "wechat_work" and self._wechat_url:
                    async with httpx.AsyncClient(trust_env=False, timeout=self._timeout) as client:
                        await client.post(
                            self._wechat_url,
                            json={"msgtype": "markdown", "markdown": {"content": full}},
                        )
                elif channel == "email" and self._email_host and self._email_to:
                    msg = EmailMessage()
                    msg["From"] = self._email_from or self._email_user
                    msg["To"] = ", ".join(self._email_to)
                    msg["Subject"] = f"[爬虫平台] {event}"
                    msg.set_content(text)
                    smtp = aiosmtplib.SMTP(
                        hostname=self._email_host,
                        port=self._email_port,
                        use_tls=self._email_ssl,
                        timeout=self._timeout,
                    )
                    await smtp.connect()
                    try:
                        if self._email_user:
                            await smtp.login(self._email_user, self._email_password)
                        await smtp.send_message(msg)
                    finally:
                        smtp.close()
                elif channel not in ("log", "webhook", "dingtalk", "wechat_work", "email"):
                    logger.warning(f"未知通知渠道，已跳过: channel={channel}")
            except Exception as e:  # noqa: BLE001 通知失败不影响主流程
                logger.error(f"通知渠道执行失败: channel={channel}, event={event}, error={e}")

    def _notify_log(self, payload: dict) -> None:
        """日志渠道：failed 走 error 级别便于告警检索，其余 info"""
        message = (
            f"[任务终态通知] task_id={payload['task_id']}, spider={payload['spider_name']}, "
            f"status={payload['status']}, result_count={payload['result_count']}, "
            f"retry_count={payload['retry_count']}"
        )
        if payload["error_message"]:
            message += f", error={payload['error_message']}"
        if payload["status"] == "failed":
            logger.error(message)
        else:
            logger.info(message)

    async def _notify_webhook(self, payload: dict) -> None:
        """Webhook 渠道：POST JSON 到配置地址

        trust_env=False：目标是外部服务时同样禁止走系统代理，
        规避本机代理软件（如 Clash）拦截 httpx 请求的陷阱。
        """
        if not self._webhook_url:
            logger.debug("NOTIFY.WEBHOOK_URL 未配置，跳过 webhook 渠道")
            return
        async with httpx.AsyncClient(trust_env=False, timeout=self._timeout) as client:
            resp = await client.post(self._webhook_url, json=payload)
            if resp.status_code >= 400:
                logger.warning(
                    f"webhook 通知返回异常状态: task_id={payload['task_id']}, "
                    f"http={resp.status_code}, body={resp.text[:200]}"
                )
            else:
                logger.info(f"webhook 通知已发送: task_id={payload['task_id']}")

    async def _notify_email(self, payload: dict) -> None:
        """Email 渠道：SMTP 发送（aiosmtplib）；SMTP_HOST/MAIL_TO 缺失时跳过"""
        if not self._email_host or not self._email_to:
            logger.debug("NOTIFY.EMAIL 未配置 SMTP_HOST/MAIL_TO，跳过 email 渠道")
            return
        msg = EmailMessage()
        msg["From"] = self._email_from or self._email_user
        msg["To"] = ", ".join(self._email_to)
        msg["Subject"] = f"[爬虫平台] 任务 #{payload['task_id']} {payload['status']}"
        msg.set_content(_render_text(payload))
        smtp = aiosmtplib.SMTP(
            hostname=self._email_host,
            port=self._email_port,
            use_tls=self._email_ssl,
            timeout=self._timeout,
        )
        await smtp.connect()
        try:
            if self._email_user:
                await smtp.login(self._email_user, self._email_password)
            await smtp.send_message(msg)
        finally:
            smtp.close()
        logger.info(f"email 通知已发送: task_id={payload['task_id']}, to={self._email_to}")

    async def _notify_dingtalk(self, payload: dict) -> None:
        """钉钉渠道：群机器人 webhook；配置了 SECRET 时附 HmacSHA256 加签"""
        if not self._dingtalk_url:
            logger.debug("NOTIFY.DINGTALK.WEBHOOK_URL 未配置，跳过 dingtalk 渠道")
            return
        url = self._dingtalk_url
        if self._dingtalk_secret:
            timestamp = str(round(time.time() * 1000))
            string_to_sign = f"{timestamp}\n{self._dingtalk_secret}"
            digest = hmac.new(
                self._dingtalk_secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                hashlib.sha256,
            ).digest()
            sign = urllib.parse.quote_plus(base64.b64encode(digest))
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}timestamp={timestamp}&sign={sign}"
        body = {"msgtype": "text", "text": {"content": _render_text(payload)}}
        async with httpx.AsyncClient(trust_env=False, timeout=self._timeout) as client:
            resp = await client.post(url, json=body)
            if resp.status_code >= 400:
                logger.warning(
                    f"dingtalk 通知返回异常状态: task_id={payload['task_id']}, "
                    f"http={resp.status_code}, body={resp.text[:200]}"
                )
            else:
                logger.info(f"dingtalk 通知已发送: task_id={payload['task_id']}")

    async def _notify_wechat_work(self, payload: dict) -> None:
        """企业微信渠道：群机器人 webhook，markdown 消息"""
        if not self._wechat_url:
            logger.debug("NOTIFY.WECHAT_WORK.WEBHOOK_URL 未配置，跳过 wechat_work 渠道")
            return
        body = {"msgtype": "markdown", "markdown": {"content": _render_text(payload)}}
        async with httpx.AsyncClient(trust_env=False, timeout=self._timeout) as client:
            resp = await client.post(self._wechat_url, json=body)
            if resp.status_code >= 400:
                logger.warning(
                    f"wechat_work 通知返回异常状态: task_id={payload['task_id']}, "
                    f"http={resp.status_code}, body={resp.text[:200]}"
                )
            else:
                logger.info(f"wechat_work 通知已发送: task_id={payload['task_id']}")
