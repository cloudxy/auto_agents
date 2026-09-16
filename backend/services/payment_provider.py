"""支付通道：在线通道（支付宝/微信）走真实网关生成可支付链接/二维码；
未配置商户凭据时拒绝（不降级伪造一个假链接）；线下挂账保留人工确认路径。

真实签名/验签实现在 `backend/services/payment_gateways/`；本模块只做
"取商户凭据 → 选通道 → 调网关 → 包成 PaymentIntent" 的编排，不碰密钥细节。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.payment_channel_credential_repository import (
    PaymentChannelCredentialRepository,
)
from backend.services.llm_secret_vault import LlmSecretVault
from backend.services.payment_gateways.alipay_gateway import AlipayGateway
from backend.services.payment_gateways.secrets_schema import (
    parse_alipay_secrets,
    parse_wechat_secrets,
)
from backend.services.payment_gateways.qr import code_url_to_svg_data_uri
from backend.services.payment_gateways.wechat_gateway import WechatGateway
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger

logger = get_logger("service.payment")

_ONLINE_CHANNELS = frozenset({"alipay", "wechat"})


@dataclass(frozen=True)
class PaymentIntent:
    status: str
    channel: str
    checkout_url: Optional[str] = None  # 支付宝：可直接跳转/新窗口打开的收银台链接
    qr_code_url: Optional[str] = None   # 微信：原始 code_url（复制链接用）
    qr_code_image: Optional[str] = None  # 微信：code_url 渲染成的 SVG data URI，前端直接 <img src>
    note: str = ""


def _public_base_url() -> str:
    from config import settings

    base = str(settings.get("PAYMENT.PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    if not base:
        raise BusinessException(
            message="平台未配置 PAYMENT.PUBLIC_BASE_URL，无法生成支付回调地址，"
                    "请联系超管在环境配置里补上本服务对外可达的域名后重试",
            code="PAYMENT_PUBLIC_BASE_URL_MISSING",
        )
    return base


async def _load_plain_secrets(session: AsyncSession, channel: str) -> tuple[str, str]:
    """返回 (merchant_no, 解密后的 secrets JSON 明文)；未配置抛 PAYMENT_NOT_CONFIGURED。"""
    repo = PaymentChannelCredentialRepository(session)
    row = await repo.get_by_channel(channel)
    if row is None:
        raise BusinessException(
            message=f"{channel} 尚未配置商户凭据，请先在后台「支付渠道」配置后再使用在线支付",
            code="PAYMENT_NOT_CONFIGURED",
        )
    plain = LlmSecretVault.decrypt_api_key(str(row.secrets_encrypted or ""))
    if not plain:
        raise BusinessException(
            message=f"{channel} 商户凭据解密失败（主密钥缺失或密文损坏），请重新在后台录入",
            code="PAYMENT_SECRETS_DECRYPT_FAILED",
        )
    return str(row.merchant_no or ""), plain


async def _alipay_intent(
    session: AsyncSession, *, order_no: str, amount_cents: int, subject: str,
) -> PaymentIntent:
    from config import settings

    _merchant_no, plain = await _load_plain_secrets(session, "alipay")
    secrets = parse_alipay_secrets(plain)
    sandbox = bool(settings.get("PAYMENT.ALIPAY.SANDBOX", False))
    gateway_url = str(settings.get(
        "PAYMENT.ALIPAY.SANDBOX_GATEWAY" if sandbox else "PAYMENT.ALIPAY.GATEWAY", "",
    ))
    gw = AlipayGateway(secrets, gateway_url=gateway_url)
    notify_url = f"{_public_base_url()}/external/v1/payments/alipay/notify"
    url = await asyncio.to_thread(
        gw.build_page_pay_url,
        out_trade_no=order_no, amount_cents=amount_cents, subject=subject,
        notify_url=notify_url,
    )
    return PaymentIntent(status="pending", channel="alipay", checkout_url=url)


async def _wechat_intent(
    session: AsyncSession, *, order_no: str, amount_cents: int, subject: str,
) -> PaymentIntent:
    from config import settings

    _merchant_no, plain = await _load_plain_secrets(session, "wechat")
    secrets = parse_wechat_secrets(plain)
    cert_dir = str(settings.get("PAYMENT.WECHAT.CERT_DIR", "storage/wechat_certs"))
    sandbox = bool(settings.get("PAYMENT.WECHAT.SANDBOX", False))

    def _build() -> str:
        gw = WechatGateway(secrets, cert_dir=cert_dir, sandbox=sandbox)
        return gw.create_native_pay(
            out_trade_no=order_no, amount_cents=amount_cents, description=subject,
            notify_url=f"{_public_base_url()}/external/v1/payments/wechat/notify",
        )

    code_url = await asyncio.to_thread(_build)
    qr_image = code_url_to_svg_data_uri(code_url)
    return PaymentIntent(
        status="pending", channel="wechat", qr_code_url=code_url, qr_code_image=qr_image,
    )


async def create_payment_intent(
    session: AsyncSession, *, channel: Optional[str], order_no: str,
    amount_cents: int, subject: str,
) -> PaymentIntent:
    """按通道创建支付意图。channel 为 None/非在线通道 → 线下挂账（不扣款）。"""
    logger.info(f"创建支付意图 | channel={channel} order_no={order_no} amount={amount_cents}")
    if channel not in _ONLINE_CHANNELS:
        return PaymentIntent(status="pending", channel="offline", note="等待人工确认收款")
    if channel == "alipay":
        return await _alipay_intent(session, order_no=order_no, amount_cents=amount_cents, subject=subject)
    return await _wechat_intent(session, order_no=order_no, amount_cents=amount_cents, subject=subject)
