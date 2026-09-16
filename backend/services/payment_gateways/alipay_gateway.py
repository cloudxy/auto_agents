"""支付宝电脑网站支付（`alipay.trade.page.pay`）：RSA2 签名 + 回调验签。

协议依据：支付宝开放平台文档《电脑网站支付》+《异步通知验签》。签名算法是
公开且长期稳定的规范（排序拼接 key=value 用 & 连接 → RSA-SHA256 签名/验签），
直接用项目已有的 `cryptography` 库实现，不额外引入 `pycryptodome`。

密钥格式：支付宝开放平台的"密钥生成工具"默认只给纯 base64 内容（无 PEM
头尾、不分行），`_normalize_pem` 兼容这种粘贴形式，也兼容标准 PEM 输入。
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import quote_plus

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from backend.services.payment_gateways.secrets_schema import AlipaySecrets
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger

logger = get_logger("service.payment.alipay")

_METHOD = "alipay.trade.page.pay"
_PRODUCT_CODE = "FAST_INSTANT_TRADE_PAY"
# 参与签名/验签时被排除的字段（sign 本身，以及只在业务层用不进签名的 sign_type
# 若出现在被验对象里也一并剔除——与支付宝官方 SDK 行为一致）
_EXCLUDE_FROM_SIGN = {"sign", "sign_type"}


def _normalize_pem(content: str, header: str) -> bytes:
    """兼容"纯 base64 无 PEM 头尾"（支付宝密钥生成工具默认输出）与标准 PEM。"""
    text = content.strip()
    if text.startswith("-----BEGIN"):
        return text.encode("utf-8")
    body = "".join(text.split())  # 去掉所有空白/换行，重新按 64 列折行
    lines = [body[i:i + 64] for i in range(0, len(body), 64)]
    pem = f"-----BEGIN {header}-----\n" + "\n".join(lines) + f"\n-----END {header}-----\n"
    return pem.encode("utf-8")


def _load_private_key(pem_content: str) -> rsa.RSAPrivateKey:
    try:
        key = serialization.load_pem_private_key(
            _normalize_pem(pem_content, "PRIVATE KEY"), password=None,
        )
    except ValueError:
        # 部分工具导出 PKCS1（RSA PRIVATE KEY）而非 PKCS8（PRIVATE KEY），头尾不同再试一次
        key = serialization.load_pem_private_key(
            _normalize_pem(pem_content, "RSA PRIVATE KEY"), password=None,
        )
    if not isinstance(key, rsa.RSAPrivateKey):
        raise BusinessException(
            message="支付宝商户私钥不是 RSA 密钥", code="PAYMENT_SECRETS_INVALID_KEY",
        )
    return key


def _load_public_key(pem_content: str) -> rsa.RSAPublicKey:
    key = serialization.load_pem_public_key(_normalize_pem(pem_content, "PUBLIC KEY"))
    if not isinstance(key, rsa.RSAPublicKey):
        raise BusinessException(
            message="支付宝公钥不是 RSA 密钥", code="PAYMENT_SECRETS_INVALID_KEY",
        )
    return key


def _ordered_query(data: dict) -> str:
    """排序拼接 key=value（& 连接），过滤空值——签名前的规范化字符串。"""
    items = sorted(
        (k, v) for k, v in data.items()
        if k not in _EXCLUDE_FROM_SIGN and v not in (None, "")
    )
    return "&".join(f"{k}={v}" for k, v in items)


def _cents_to_yuan(amount_cents: int) -> str:
    yuan = (Decimal(amount_cents) / Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )
    return str(yuan)


class AlipayGateway:
    """一次调用绑定一套商户密钥（不缓存跨请求状态，密钥轮换零延迟生效）。"""

    def __init__(self, secrets: AlipaySecrets, *, gateway_url: str):
        self._app_id = secrets.app_id
        self._private_key = _load_private_key(secrets.app_private_key)
        self._public_key = _load_public_key(secrets.alipay_public_key)
        self._gateway_url = gateway_url

    def _sign(self, message: str) -> str:
        import base64

        signature = self._private_key.sign(
            message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def build_page_pay_url(
        self, *, out_trade_no: str, amount_cents: int, subject: str,
        notify_url: str, return_url: str | None = None,
    ) -> str:
        """电脑网站支付：返回一个可直接 302/window.open 的完整收银台 URL。"""
        biz_content = {
            "out_trade_no": out_trade_no,
            "total_amount": _cents_to_yuan(amount_cents),
            "subject": subject,
            "product_code": _PRODUCT_CODE,
        }
        params: dict[str, str] = {
            "app_id": self._app_id,
            "method": _METHOD,
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "notify_url": notify_url,
            "biz_content": json.dumps(biz_content, ensure_ascii=False, separators=(",", ":")),
        }
        if return_url:
            params["return_url"] = return_url
        unsigned = _ordered_query(params)
        params["sign"] = self._sign(unsigned)
        query = "&".join(f"{k}={quote_plus(v)}" for k, v in params.items())
        logger.info(f"alipay.page_pay 构造收银台链接 | out_trade_no={out_trade_no}")
        return f"{self._gateway_url}?{query}"

    def verify_notify(self, form: dict) -> bool:
        """验证异步通知的 RSA2 签名（业务四要素核对由调用方另做）。"""
        import base64

        sign = str(form.get("sign") or "")
        if not sign:
            return False
        message = _ordered_query({k: str(v) for k, v in form.items()})
        try:
            self._public_key.verify(
                base64.b64decode(sign), message.encode("utf-8"),
                padding.PKCS1v15(), hashes.SHA256(),
            )
            return True
        except (InvalidSignature, ValueError) as exc:
            logger.warning(f"alipay.notify 验签失败 | err={exc}")
            return False
