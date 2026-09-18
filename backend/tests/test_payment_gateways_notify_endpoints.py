"""真实网关回调端点（/external/v1/payments/{alipay,wechat}/notify）：
签名验真通过后走 PaymentNotifyService.handle_verified_fields 履约；
签名不对/四要素不符时保持未开通，响应仍是对方协议要求的"收到"格式。
"""
from __future__ import annotations

import json

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from backend.tests.payment_notify_support import install_fernet, order_row, put_channel, seed_plans
from conftest import make_tenant_owner_headers

ALIPAY_NOTIFY = "/external/v1/payments/alipay/notify"
WECHAT_NOTIFY = "/external/v1/payments/wechat/notify"
CHECKOUT = "/api/v1/billing/checkout"


def _keypair():
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
    return key, priv, pub


def _sign_form(private_key, form: dict) -> str:
    import base64

    message = "&".join(f"{k}={v}" for k, v in sorted(form.items()))
    sig = private_key.sign(message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode("utf-8")


def _alipay_checkout(db_client, db_session, *, merchant_no: str):
    """建一个 alipay 商户凭据（真实 JSON 形状）+ 一笔 checkout_pending 订单。"""
    _key, priv, pub = _keypair()
    secrets = json.dumps({"app_id": "2021000000000000", "app_private_key": priv, "alipay_public_key": pub})
    pa = put_channel(db_client, db_session, "alipay", secret=secrets)[0]
    # put_channel 生成的 merchant_no 是随机的；改成调用方指定值，保证四要素能对上
    db_client.put("/api/v1/admin/payment-credentials", headers=pa, json={
        "channel": "alipay", "merchant_no": merchant_no, "secrets": secrets,
    })
    seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="qa-alipay-live")
    resp = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro", "channel": "alipay"})
    assert resp.status_code == 201, resp.text
    order = resp.json()["data"]
    return priv, order, tid


def test_alipay_real_notify_fulfills_order(db_client, db_session, monkeypatch):
    install_fernet(monkeypatch)
    merchant_no = "2088611100000000"
    priv, order, _tid = _alipay_checkout(db_client, db_session, merchant_no=merchant_no)

    key = serialization.load_pem_private_key(priv.encode(), password=None)
    form = {
        "out_trade_no": order["order_no"], "trade_status": "TRADE_SUCCESS",
        "total_amount": "299.00", "seller_id": merchant_no, "trade_no": "2026091622001",
    }
    form["sign"] = _sign_form(key, form)

    resp = db_client.post(ALIPAY_NOTIFY, data=form)
    assert resp.status_code == 200
    assert resp.text == "success"

    row = order_row(db_session, _tid_of(order))
    assert row is not None
    assert row["status"] in ("paid_pending_fulfillment", "fulfilled")
    assert row["verified"] is not None


def test_alipay_real_notify_rejects_tampered_signature(db_client, db_session, monkeypatch):
    install_fernet(monkeypatch)
    merchant_no = "2088611100000001"
    priv, order, tid = _alipay_checkout(db_client, db_session, merchant_no=merchant_no)

    key = serialization.load_pem_private_key(priv.encode(), password=None)
    form = {
        "out_trade_no": order["order_no"], "trade_status": "TRADE_SUCCESS",
        "total_amount": "299.00", "seller_id": merchant_no,
    }
    form["sign"] = _sign_form(key, form)
    form["total_amount"] = "1.00"  # 签名后再篡改金额

    resp = db_client.post(ALIPAY_NOTIFY, data=form)
    assert resp.status_code == 200
    assert resp.text == "success"  # 协议要求仍回 success，不重试

    row = order_row(db_session, tid)
    assert row is not None
    assert row["status"] == "checkout_pending"  # 未开通
    assert row["verified"] is None


def test_alipay_notify_no_credentials_configured_is_noop(db_client, db_session, monkeypatch):
    install_fernet(monkeypatch)
    resp = db_client.post(ALIPAY_NOTIFY, data={"out_trade_no": "ghost", "trade_status": "TRADE_SUCCESS"})
    assert resp.status_code == 200
    assert resp.text == "success"


def test_wechat_real_notify_fulfills_order_via_stubbed_gateway(db_client, db_session, monkeypatch):
    """WeChatPay 真实构造触发证书下载（网络副作用），打桩隔离，只验证端点的
    验真结果 → handle_verified_fields 接线是否正确。"""
    install_fernet(monkeypatch)
    import backend.app.external_api.v1.payment_gateways as endpoint_mod

    secrets = json.dumps({
        "mch_id": "1900000109", "api_v3_key": "x" * 32, "apiclient_key": "dummy",
        "cert_serial_no": "ABC", "appid": "wxdummy",
    })
    pa, _secret, _merchant = put_channel(db_client, db_session, "wechat", secret=secrets)
    merchant_no = "1900000109"
    db_client.put("/api/v1/admin/payment-credentials", headers=pa, json={
        "channel": "wechat", "merchant_no": merchant_no, "secrets": secrets,
    })
    seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="qa-wechat-live")
    resp = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro", "channel": "wechat"})
    assert resp.status_code == 201, resp.text
    order = resp.json()["data"]

    class _StubGateway:
        def __init__(self, secrets, *, cert_dir, sandbox=False):
            pass

        def verify_and_decrypt_notify(self, headers, body):
            return {
                "resource": {
                    "out_trade_no": order["order_no"], "trade_state": "SUCCESS",
                    "amount": {"total": 29900}, "mchid": merchant_no,
                    "transaction_id": "4200001234202609",
                },
            }

    monkeypatch.setattr(endpoint_mod, "WechatGateway", _StubGateway)

    resp = db_client.post(WECHAT_NOTIFY, content=b"{}", headers={"Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json() == {"code": "SUCCESS", "message": "成功"}

    row = order_row(db_session, tid)
    assert row is not None
    assert row["status"] in ("paid_pending_fulfillment", "fulfilled")


def _tid_of(order: dict) -> int:
    return int(order["tenant_id"])
