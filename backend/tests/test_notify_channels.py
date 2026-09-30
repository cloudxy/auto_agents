"""通知渠道由配置推导（审计 BUG-36 回归）：配置页填了地址的渠道要真的发送；支持测试发送"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.services.notify_service import NotifyService


class _Recorder:
    def __init__(self):
        self.posts: list[tuple[str, dict]] = []

    def transport(self):
        def handler(request: httpx.Request) -> httpx.Response:
            import json

            self.posts.append((str(request.url), json.loads(request.content or b"{}")))
            return httpx.Response(200)
        return httpx.MockTransport(handler)


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    real = httpx.AsyncClient

    class _Client(real):
        def __init__(self, *a, **kw):
            kw["transport"] = rec.transport()
            super().__init__(*a, **kw)

    monkeypatch.setattr("backend.services.notify_service.httpx.AsyncClient", _Client)
    return rec


def test_configured_url_enables_channel(monkeypatch, recorder):
    svc = NotifyService()
    svc._channels = ["log"]  # 配置文件只声明 log（默认值）

    async def _url(channel):
        return "https://hooks.example.com/ops" if channel == "webhook" else ""

    monkeypatch.setattr(svc, "_channel_url", _url)
    asyncio.run(svc.notify_text("task.failed", "任务 7 失败"))
    assert recorder.posts and recorder.posts[0][0] == "https://hooks.example.com/ops"


def test_no_url_no_extra_channel(monkeypatch, recorder):
    svc = NotifyService()
    svc._channels = ["log"]

    async def _url(channel):
        return ""

    monkeypatch.setattr(svc, "_channel_url", _url)
    asyncio.run(svc.notify_text("x", "y"))
    assert recorder.posts == []


def test_send_test_endpoint(db_client, platform_admin_client, monkeypatch, recorder):
    async def _url(self, channel):
        return "https://oapi.dingtalk.example/robot" if channel == "dingtalk" else ""

    monkeypatch.setattr(NotifyService, "_channel_url", _url)
    ok = platform_admin_client.post("/api/v1/admin/notify-config/test", json={"channel": "dingtalk"})
    assert ok.status_code == 200 and ok.json()["data"]["sent"] is True
    assert recorder.posts[-1][1]["msgtype"] == "text"
    missing = platform_admin_client.post("/api/v1/admin/notify-config/test", json={"channel": "webhook"})
    assert missing.json()["data"] == {"channel": "webhook", "sent": False, "reason": "该渠道尚未配置地址"}


def test_send_test_tenant_admin_404(admin_client):
    assert admin_client.post("/api/v1/admin/notify-config/test", json={"channel": "webhook"}).status_code == 404


def test_send_test_unknown_channel_is_422(platform_admin_client):
    """未知渠道 → 422 业务错误（原先缺 BusinessException 导入，此路径 NameError 成 500）"""
    resp = platform_admin_client.post("/api/v1/admin/notify-config/test", json={"channel": "carrier-pigeon"})
    assert resp.status_code == 422
    assert resp.json()["code"] == "NOTIFY_CHANNEL_INVALID"
