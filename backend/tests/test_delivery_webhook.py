"""C5 租户交付 webhook：签名头 + 成功投递；SSRF 与租户独立密钥（审计 BUG-22 / P0-8）。"""
import asyncio
import hashlib
import hmac

import httpx
import pytest

from backend.services.delivery_webhook_service import DeliveryWebhookService


def _recording(seen: list, status: int = 200, headers: dict | None = None):
    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, headers=headers or {})
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_deliver_includes_hmac_and_succeeds():
    seen: list = []
    ok = await DeliveryWebhookService().deliver(
        "https://hooks.example.com/hook",
        {"task_id": 7, "event": "task.finished"},
        secret="abc",
        transport=_recording(seen),
    )
    assert ok is True
    req = seen[0]
    ts, sig = req.headers["x-webhook-timestamp"], req.headers["x-webhook-signature"]
    expected = hmac.new(b"abc", f"{ts}.".encode() + req.content, hashlib.sha256).hexdigest()
    assert sig == expected  # 租户可用自己的密钥验签


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "http://127.0.0.1/hook",
    "http://169.254.169.254/latest/meta-data/",
    "http://hook.127-0-0-1.nip.io/x",       # 域名解析到环回（DNS 桩）
    "http://[::ffff:127.0.0.1]/hook",       # IPv4-mapped IPv6
    "http://2130706433/hook",               # 整数编码 IP
])
async def test_deliver_refuses_internal_targets_with_zero_requests(url, monkeypatch):
    monkeypatch.setattr("backend.services.delivery_webhook_service.asyncio.sleep", _no_sleep)
    seen: list = []
    ok = await DeliveryWebhookService().deliver(url, {"task_id": 1}, secret="s", transport=_recording(seen))
    assert ok is False
    assert seen == []


async def _no_sleep(_s):
    return None


@pytest.mark.asyncio
async def test_deliver_does_not_follow_redirect(monkeypatch):
    """302 跳内网：不跟随，且 3xx 不算投递成功"""
    monkeypatch.setattr("backend.services.delivery_webhook_service.asyncio.sleep", _no_sleep)
    seen: list = []
    ok = await DeliveryWebhookService().deliver(
        "https://hooks.example.com/hook", {"task_id": 2}, secret="s",
        transport=_recording(seen, 302, {"location": "http://10.0.0.5/internal"}),
    )
    assert ok is False
    assert all(r.url.host == "hooks.example.com" for r in seen)


def _owner(db_session):
    from conftest import make_tenant_owner_headers
    return make_tenant_owner_headers(db_session, slug="hook-co")


URL = "/api/v1/tenants/me/delivery-webhook"


def test_set_webhook_rejects_private_address(db_client, db_session):
    headers, _tid = _owner(db_session)
    resp = db_client.put(URL, json={"url": "http://192.168.1.10/hook"}, headers=headers)
    assert resp.status_code == 422
    assert db_client.get(URL, headers=headers).json()["data"]["delivery_webhook_url"] is None


def test_set_webhook_issues_tenant_secret_and_rotates(db_client, db_session):
    headers, _tid = _owner(db_session)
    first = db_client.put(URL, json={"url": "https://hooks.example.com/a"}, headers=headers)
    assert first.status_code == 200, first.text
    secret = first.json()["data"]["signing_secret"]
    assert secret and secret.startswith("whsec_")
    # 改地址不换密钥；显式轮换才换
    again = db_client.put(URL, json={"url": "https://hooks.example.com/b"}, headers=headers)
    assert again.json()["data"]["signing_secret"] == secret
    rotated = db_client.put(URL, json={"url": "https://hooks.example.com/b", "rotate_secret": True},
                            headers=headers)
    assert rotated.json()["data"]["signing_secret"] not in (None, secret)


def test_delivery_uses_tenant_secret(db_session, db_client):
    from backend.services.tenant_settings_service import TenantSettingsService

    headers, tid = _owner(db_session)
    db_client.put(URL, json={"url": "https://hooks.example.com/a"}, headers=headers)

    async def _cfg():
        async with db_session() as s:
            return await TenantSettingsService(s).get_delivery_config(tid)

    url, secret = asyncio.run(_cfg())
    assert url == "https://hooks.example.com/a" and secret.startswith("whsec_")
