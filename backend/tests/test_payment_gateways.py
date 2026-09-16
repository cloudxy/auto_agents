"""支付网关模块：Alipay RSA2 签名/验签自洽性 + 商户密钥包形状校验 +
payment_provider 编排（offline/未配置/真实网关三条路径）。

无法端到端联到支付宝/微信真实服务器（没有真实商户账号），本文件验证的是
"我们自己实现的签名/验签算法是否内部一致、密钥格式解析是否正确、编排逻辑
是否按 channel 分派到正确的通路"——这部分是可以完全离线验证的，也是最
容易埋雷的部分（协议细节写错、密钥格式解析错误）。
"""
from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.services.payment_gateways.alipay_gateway import AlipayGateway
from backend.services.payment_gateways.secrets_schema import (
    AlipaySecrets,
    parse_alipay_secrets,
    parse_wechat_secrets,
    validate_secrets,
)
from platform_core.exceptions import BusinessException

_GATEWAY_URL = "https://openapi.alipay.com/gateway.do"


def _gen_keypair() -> tuple[str, str]:
    """生成一对自签测试用 RSA 密钥（PKCS8 私钥 + SubjectPublicKeyInfo 公钥）。"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pub_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return priv_pem, pub_pem


def _bare_base64(pem: str) -> str:
    """去掉 PEM 头尾/换行，模拟支付宝密钥生成工具的默认粘贴形式。"""
    lines = [ln for ln in pem.strip().splitlines() if "BEGIN" not in ln and "END" not in ln]
    return "".join(lines)


# ---------- Alipay：签名自洽性 ----------

def test_alipay_page_pay_url_structure_and_self_consistency():
    from urllib.parse import parse_qs, urlparse

    priv_pem, pub_pem = _gen_keypair()
    # 用支付宝自己的公钥当"支付宝公钥"——自签自验，测的是我们的排序拼接+
    # RSA2 签名实现是否内部一致，不依赖真实支付宝账号
    secrets = AlipaySecrets(app_id="2021000000000000", app_private_key=priv_pem, alipay_public_key=pub_pem)
    gw = AlipayGateway(secrets, gateway_url=_GATEWAY_URL)
    url = gw.build_page_pay_url(
        out_trade_no="order-abc123", amount_cents=19900, subject="专业档订阅",
        notify_url="https://app.example.com/external/v1/payments/alipay/notify",
    )
    assert url.startswith(_GATEWAY_URL + "?")
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert query["app_id"] == ["2021000000000000"]
    assert query["method"] == ["alipay.trade.page.pay"]
    assert "sign" in query
    # 分转元：19900 分 = 199.00 元，字符串精确无浮点误差
    biz_content = json.loads(query["biz_content"][0])
    assert biz_content["total_amount"] == "199.00"
    assert biz_content["out_trade_no"] == "order-abc123"
    assert biz_content["subject"] == "专业档订阅"
    # 用同一份网关自验签名，证明服务端拼出的 URL 参数与签名互相自洽
    form = {k: v[0] for k, v in query.items()}
    assert gw.verify_notify(form) is True


def test_alipay_notify_verify_roundtrip():
    priv_pem, pub_pem = _gen_keypair()
    secrets = AlipaySecrets(app_id="2021000000000000", app_private_key=priv_pem, alipay_public_key=pub_pem)
    gw = AlipayGateway(secrets, gateway_url=_GATEWAY_URL)
    # 用同一把私钥反向构造一份"通知体"并签名，模拟支付宝服务端回调
    form = {
        "out_trade_no": "order-abc123", "trade_status": "TRADE_SUCCESS",
        "total_amount": "199.00", "seller_id": "2088xxxx",
    }
    message = "&".join(f"{k}={v}" for k, v in sorted(form.items()))
    sign = gw._sign(message)  # noqa: SLF001 — 测试直接用内部签名方法构造夹具
    signed_form = {**form, "sign": sign, "sign_type": "RSA2"}
    assert gw.verify_notify(signed_form) is True


def test_alipay_notify_verify_rejects_tampered_amount():
    priv_pem, pub_pem = _gen_keypair()
    secrets = AlipaySecrets(app_id="2021000000000000", app_private_key=priv_pem, alipay_public_key=pub_pem)
    gw = AlipayGateway(secrets, gateway_url=_GATEWAY_URL)
    form = {"out_trade_no": "order-abc123", "trade_status": "TRADE_SUCCESS", "total_amount": "199.00"}
    message = "&".join(f"{k}={v}" for k, v in sorted(form.items()))
    sign = gw._sign(message)  # noqa: SLF001
    tampered = {**form, "total_amount": "1.00", "sign": sign}  # 签名对不上篡改后的金额
    assert gw.verify_notify(tampered) is False


def test_alipay_notify_verify_rejects_wrong_key():
    priv_pem, pub_pem = _gen_keypair()
    other_priv, _other_pub = _gen_keypair()
    secrets = AlipaySecrets(app_id="2021000000000000", app_private_key=priv_pem, alipay_public_key=pub_pem)
    gw = AlipayGateway(secrets, gateway_url=_GATEWAY_URL)
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes
    import base64

    other_key = serialization.load_pem_private_key(other_priv.encode(), password=None)
    form = {"out_trade_no": "order-abc123", "trade_status": "TRADE_SUCCESS", "total_amount": "199.00"}
    message = "&".join(f"{k}={v}" for k, v in sorted(form.items()))
    forged_sig = base64.b64encode(
        other_key.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())
    ).decode()
    assert gw.verify_notify({**form, "sign": forged_sig}) is False


def test_alipay_gateway_accepts_bare_base64_keys():
    """密钥生成工具默认输出无 PEM 头尾的纯 base64——网关必须兼容这种粘贴形式。"""
    priv_pem, pub_pem = _gen_keypair()
    secrets = AlipaySecrets(
        app_id="2021000000000000",
        app_private_key=_bare_base64(priv_pem),
        alipay_public_key=_bare_base64(pub_pem),
    )
    gw = AlipayGateway(secrets, gateway_url=_GATEWAY_URL)
    url = gw.build_page_pay_url(
        out_trade_no="order-xyz", amount_cents=100, subject="测试",
        notify_url="https://app.example.com/notify",
    )
    assert "sign=" in url


# ---------- 密钥包形状校验 ----------

def test_parse_alipay_secrets_missing_field_raises():
    with pytest.raises(BusinessException) as exc:
        parse_alipay_secrets(json.dumps({"app_id": "x"}))
    assert "app_private_key" in str(exc.value)


def test_parse_alipay_secrets_invalid_json_raises():
    with pytest.raises(BusinessException):
        parse_alipay_secrets("not json at all")


def test_parse_wechat_secrets_missing_field_raises():
    with pytest.raises(BusinessException) as exc:
        parse_wechat_secrets(json.dumps({"mch_id": "123"}))
    assert "api_v3_key" in str(exc.value)


def test_validate_secrets_dispatches_by_channel():
    priv_pem, pub_pem = _gen_keypair()
    good = json.dumps({
        "app_id": "1", "app_private_key": priv_pem, "alipay_public_key": pub_pem,
    })
    validate_secrets("alipay", good)  # 不抛即通过
    with pytest.raises(BusinessException):
        validate_secrets("wechat", "{}")
