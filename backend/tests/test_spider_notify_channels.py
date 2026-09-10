"""通知渠道扩展测试（email / dingtalk / wechat_work）

约定：不连真实 SMTP/外部服务，aiosmtplib/httpx 用 MagicMock 桩。
覆盖：三个新渠道发送路径、加签、未配置跳过、未知渠道告警回归、文案渲染。
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.notify_service import NotifyService, _render_text  # noqa: E402


def _payload() -> dict:
    return {
        "event": "task.finished", "task_id": 7, "spider_name": "example",
        "status": "failed", "result_count": 3, "retry_count": 2,
        "error_message": "boom",
    }


async def _notify(svc: NotifyService) -> None:
    await svc.notify_task_finished(
        task_id=7, spider_name="example", status="failed",
        result_count=3, retry_count=2, error_message="boom",
    )


def _httpx_stub(status_code=200):
    resp = MagicMock(status_code=status_code, text="ok")
    client = MagicMock()
    client.post = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ---------------- 文案渲染 ----------------
def test_render_text_contains_key_fields():
    text = _render_text(_payload())
    assert "#7" in text
    assert "example" in text
    assert "failed" in text
    assert "boom" in text


# ---------------- email ----------------
class TestEmailChannel:
    @pytest.mark.asyncio
    async def test_email_sends_via_smtp(self):
        svc = NotifyService()
        svc._channels = ["email"]
        svc._email_host = "smtp.example.com"
        svc._email_port = 465
        svc._email_user = "bot@example.com"
        svc._email_password = "secret"
        svc._email_ssl = True
        svc._email_from = "bot@example.com"
        svc._email_to = ["ops@example.com"]

        smtp = MagicMock()
        smtp.connect = AsyncMock()
        smtp.login = AsyncMock()
        smtp.send_message = AsyncMock()
        smtp.close = MagicMock()
        with patch("backend.services.notify_service.aiosmtplib.SMTP", return_value=smtp) as smtp_cls:
            await _notify(svc)

        smtp_cls.assert_called_once()
        kwargs = smtp_cls.call_args.kwargs
        assert kwargs["hostname"] == "smtp.example.com"
        assert kwargs["use_tls"] is True
        smtp.login.assert_awaited_once_with("bot@example.com", "secret")
        smtp.send_message.assert_awaited_once()
        msg = smtp.send_message.await_args.args[0]
        assert msg["To"] == "ops@example.com"
        assert "#7" in msg["Subject"]

    @pytest.mark.asyncio
    async def test_email_skipped_without_config(self):
        svc = NotifyService()
        svc._channels = ["email"]
        svc._email_host = ""
        svc._email_to = []
        with patch("backend.services.notify_service.aiosmtplib.SMTP") as smtp_cls:
            await _notify(svc)
        smtp_cls.assert_not_called()


# ---------------- dingtalk ----------------
class TestDingtalkChannel:
    @pytest.mark.asyncio
    async def test_dingtalk_posts_with_signature(self):
        svc = NotifyService()
        svc._channels = ["dingtalk"]
        svc._dingtalk_url = "https://oapi.dingtalk.com/robot/send?access_token=t"
        svc._dingtalk_secret = "SEC-demo-secret"

        client = _httpx_stub()
        with patch("backend.services.notify_service.httpx.AsyncClient", return_value=client):
            await _notify(svc)

        client.post.assert_awaited_once()
        url = client.post.await_args.args[0]
        assert "timestamp=" in url and "sign=" in url
        assert url.startswith("https://oapi.dingtalk.com/robot/send?access_token=t&")
        body = client.post.await_args.kwargs["json"]
        assert body["msgtype"] == "text"
        assert "#7" in body["text"]["content"]

    @pytest.mark.asyncio
    async def test_dingtalk_without_secret_no_signature(self):
        svc = NotifyService()
        svc._channels = ["dingtalk"]
        svc._dingtalk_url = "https://oapi.dingtalk.com/robot/send?access_token=t"
        svc._dingtalk_secret = ""

        client = _httpx_stub()
        with patch("backend.services.notify_service.httpx.AsyncClient", return_value=client):
            await _notify(svc)

        url = client.post.await_args.args[0]
        assert "sign=" not in url  # 未配置密钥不加签

    @pytest.mark.asyncio
    async def test_dingtalk_skipped_without_url(self):
        svc = NotifyService()
        svc._channels = ["dingtalk"]
        svc._dingtalk_url = ""
        client = _httpx_stub()
        with patch("backend.services.notify_service.httpx.AsyncClient", return_value=client):
            await _notify(svc)
        client.post.assert_not_awaited()


# ---------------- wechat_work ----------------
class TestWechatWorkChannel:
    @pytest.mark.asyncio
    async def test_wechat_work_posts_markdown(self):
        svc = NotifyService()
        svc._channels = ["wechat_work"]
        svc._wechat_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=k"

        client = _httpx_stub()
        with patch("backend.services.notify_service.httpx.AsyncClient", return_value=client):
            await _notify(svc)

        client.post.assert_awaited_once()
        url = client.post.await_args.args[0]
        assert url == svc._wechat_url
        body = client.post.await_args.kwargs["json"]
        assert body["msgtype"] == "markdown"
        assert "#7" in body["markdown"]["content"]

    @pytest.mark.asyncio
    async def test_wechat_work_skipped_without_url(self):
        svc = NotifyService()
        svc._channels = ["wechat_work"]
        svc._wechat_url = ""
        client = _httpx_stub()
        with patch("backend.services.notify_service.httpx.AsyncClient", return_value=client):
            await _notify(svc)
        client.post.assert_not_awaited()


# ---------------- 未知渠道回归 + 渠道隔离 ----------------
class TestChannelRobustness:
    @pytest.mark.asyncio
    async def test_unknown_channel_warns_and_continues(self):
        svc = NotifyService()
        svc._channels = ["carrier_pigeon", "log"]
        with patch("backend.services.notify_service.logger") as fake_logger:
            await _notify(svc)
        warned = [c.args[0] for c in fake_logger.warning.call_args_list]
        assert any("carrier_pigeon" in w for w in warned)

    @pytest.mark.asyncio
    async def test_channel_failure_does_not_break_others(self):
        svc = NotifyService()
        svc._channels = ["dingtalk", "log"]
        svc._dingtalk_url = "https://oapi.dingtalk.com/robot/send?access_token=t"

        client = MagicMock()
        client.post = AsyncMock(side_effect=ConnectionError("down"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        with (
            patch("backend.services.notify_service.httpx.AsyncClient", return_value=client),
            patch("backend.services.notify_service.logger") as fake_logger,
        ):
            await _notify(svc)  # 不抛异常
        # dingtalk 失败后 log 渠道照常执行（error 级别：status=failed）
        assert fake_logger.error.call_args_list
