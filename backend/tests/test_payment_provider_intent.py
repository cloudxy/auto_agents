"""payment_provider.create_payment_intent 编排 + billing_service 结账接线：
offline / 未配置 / 已配置真实网关（alipay 真跑签名，wechat 打桩隔离网络）
三条路径，以及 create_checkout 在网关失败时优雅回退不阻断下单。
"""
from __future__ import annotations

import asyncio
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from backend.services.payment_provider import create_payment_intent
from backend.tests.payment_notify_support import install_fernet, put_channel, seed_plans
from conftest import make_tenant_owner_headers
from platform_core.exceptions import BusinessException
from platform_core.models.billing import Order

CHECKOUT = "/api/v1/billing/checkout"


def _alipay_secrets_json() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return json.dumps({"app_id": "2021000000000000", "app_private_key": priv, "alipay_public_key": pub})


def _wechat_secrets_json() -> str:
    return json.dumps({
        "mch_id": "1900000109", "api_v3_key": "x" * 32, "apiclient_key": "dummy-pem",
        "cert_serial_no": "ABC123", "appid": "wxdummy",
    })


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch):
    install_fernet(monkeypatch)


def _order_row(db_session, order_no: str):
    async def _go():
        async with db_session() as s:
            return (await s.execute(
                select(Order).where(Order.order_no == order_no)
            )).scalar_one_or_none()

    return asyncio.run(_go())


# ---------- create_payment_intent 三条路径 ----------

def test_offline_channel_returns_pending_without_gateway_call(db_session):
    async def _go():
        async with db_session() as s:
            return await create_payment_intent(
                s, channel=None, order_no="o1", amount_cents=100, subject="测试",
            )

    intent = asyncio.run(_go())
    assert intent.status == "pending"
    assert intent.channel == "offline"
    assert intent.checkout_url is None and intent.qr_code_url is None


def test_unconfigured_online_channel_raises_clear_error(db_session):
    async def _go():
        async with db_session() as s:
            await create_payment_intent(
                s, channel="alipay", order_no="o1", amount_cents=100, subject="测试",
            )

    with pytest.raises(BusinessException) as exc:
        asyncio.run(_go())
    assert "PAYMENT_NOT_CONFIGURED" in str(exc.value) or "尚未配置商户凭据" in str(exc.value)


def test_configured_alipay_without_public_base_url_raises(db_client, db_session):
    put_channel(db_client, db_session, "alipay", secret=_alipay_secrets_json())

    async def _go():
        async with db_session() as s:
            await create_payment_intent(
                s, channel="alipay", order_no="o1", amount_cents=100, subject="测试",
            )

    with pytest.raises(BusinessException) as exc:
        asyncio.run(_go())
    assert "PUBLIC_BASE_URL" in str(exc.value)


def test_configured_alipay_builds_real_checkout_url(db_client, db_session, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "get", _patched_get(settings.get, {
        "PAYMENT.PUBLIC_BASE_URL": "https://app.example.com",
    }))
    put_channel(db_client, db_session, "alipay", secret=_alipay_secrets_json())

    async def _go():
        async with db_session() as s:
            return await create_payment_intent(
                s, channel="alipay", order_no="o-real-1", amount_cents=19900, subject="专业档",
            )

    intent = asyncio.run(_go())
    assert intent.channel == "alipay"
    assert intent.checkout_url is not None
    assert intent.checkout_url.startswith("https://openapi")
    assert "o-real-1" in intent.checkout_url  # out_trade_no 编码进了 biz_content


def test_configured_wechat_builds_qr_via_stubbed_gateway(db_client, db_session, monkeypatch):
    """WechatGateway 真实构造会触发平台证书下载（网络副作用），打桩隔离。"""
    from config import settings
    import backend.services.payment_provider as provider_mod

    monkeypatch.setattr(settings, "get", _patched_get(settings.get, {
        "PAYMENT.PUBLIC_BASE_URL": "https://app.example.com",
    }))
    put_channel(db_client, db_session, "wechat", secret=_wechat_secrets_json())

    class _StubGateway:
        def __init__(self, secrets, *, cert_dir, sandbox=False):
            self.secrets = secrets

        def create_native_pay(self, *, out_trade_no, amount_cents, description, notify_url):
            assert out_trade_no == "o-wx-1"
            assert amount_cents == 19900
            assert notify_url.endswith("/external/v1/payments/wechat/notify")
            return "weixin://wxpay/bizpayurl?pr=stubbed"

    monkeypatch.setattr(provider_mod, "WechatGateway", _StubGateway)

    async def _go():
        async with db_session() as s:
            return await create_payment_intent(
                s, channel="wechat", order_no="o-wx-1", amount_cents=19900, subject="专业档",
            )

    intent = asyncio.run(_go())
    assert intent.channel == "wechat"
    assert intent.qr_code_url == "weixin://wxpay/bizpayurl?pr=stubbed"
    assert intent.qr_code_image is not None
    assert intent.qr_code_image.startswith("data:image/svg+xml;base64,")
    assert intent.checkout_url is None


def _patched_get(orig_get, overrides: dict):
    def _get(key, default=None, **kwargs):
        if key in overrides:
            return overrides[key]
        return orig_get(key, default, **kwargs)

    return _get


# ---------- billing_service.create_checkout 接线 ----------

def test_checkout_attaches_pay_url_when_channel_configured(db_client, db_session, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "get", _patched_get(settings.get, {
        "PAYMENT.PUBLIC_BASE_URL": "https://app.example.com",
    }))
    seed_plans(db_session)
    owner, _tid = make_tenant_owner_headers(db_session, slug="qa-payurl")
    put_channel(db_client, db_session, "alipay", secret=_alipay_secrets_json())

    resp = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro", "channel": "alipay"})
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["pay_url"] is not None
    assert data["pay_url"].startswith("https://openapi")
    assert data["qr_code_url"] is None


def test_pay_intent_endpoint_regenerates_link_without_reissuing_order(db_client, db_session, monkeypatch):
    """刷新结账页 / 二次打开时按需重取链接——不建新单，不改订单状态。"""
    from config import settings

    monkeypatch.setattr(settings, "get", _patched_get(settings.get, {
        "PAYMENT.PUBLIC_BASE_URL": "https://app.example.com",
    }))
    seed_plans(db_session)
    owner, _tid = make_tenant_owner_headers(db_session, slug="qa-pay-intent")
    put_channel(db_client, db_session, "alipay", secret=_alipay_secrets_json())

    created = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro", "channel": "alipay"})
    assert created.status_code == 201, created.text
    order_id = created.json()["data"]["id"]

    resp = db_client.get(f"/api/v1/billing/orders/{order_id}/pay-intent", headers=owner)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["pay_url"] is not None
    assert data["status"] == "checkout_pending"


def test_pay_intent_endpoint_rejects_other_tenants_order(db_client, db_session):
    seed_plans(db_session)
    owner_a, _tid_a = make_tenant_owner_headers(db_session, slug="qa-pi-a")
    owner_b, _tid_b = make_tenant_owner_headers(db_session, slug="qa-pi-b")
    created = db_client.post(CHECKOUT, headers=owner_a, json={"product": "plan_pro"})
    assert created.status_code == 201, created.text
    order_id = created.json()["data"]["id"]

    resp = db_client.get(f"/api/v1/billing/orders/{order_id}/pay-intent", headers=owner_b)
    assert resp.status_code == 404


def test_checkout_tolerates_gateway_failure_and_still_creates_order(db_client, db_session):
    """商户密钥包存的是 HMAC 夹具字符串（非真实 JSON）——create_payment_intent
    会因 JSON 解析失败报错，但下单本身不能被这个失败拖垮（现有 HMAC 夹具
    测试大量依赖这条兼容路径，见 payment_notify_support.put_channel 默认用法）。
    """
    seed_plans(db_session)
    owner, _tid = make_tenant_owner_headers(db_session, slug="qa-tolerant")
    put_channel(db_client, db_session, "alipay")  # 默认非 JSON 密钥字符串

    resp = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro", "channel": "alipay"})
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["status"] == "checkout_pending"
    assert data["pay_url"] is None and data["qr_code_url"] is None
    row = _order_row(db_session, data["order_no"])
    assert row is not None and row.status == "checkout_pending"
