"""支付通道：在线扣款未开通；线下挂账。"""
from dataclasses import dataclass
from typing import Protocol

from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger

logger = get_logger("service.payment")


@dataclass(frozen=True)
class PaymentIntent:
    status: str
    channel: str
    checkout_url: str | None = None
    note: str = ""


class PaymentProvider(Protocol):
    def collect(self, *, order_id: int, amount_cents: int, channel: str) -> PaymentIntent:
        ...


class OfflinePaymentProvider:
    """现行通道：不向第三方发起扣款，订单保持 pending 等人工确认。"""

    def collect(self, *, order_id: int, amount_cents: int, channel: str) -> PaymentIntent:
        logger.info(f"线下挂账不扣款 | order={order_id} amount={amount_cents}")
        return PaymentIntent(
            status="pending", channel="offline", note="等待人工确认收款",
        )


class UnconfiguredOnlineProvider:
    """支付宝/微信骨架：通道位预留，未接密钥与回调。"""

    def collect(self, *, order_id: int, amount_cents: int, channel: str) -> PaymentIntent:
        logger.info(f"在线支付未开通 | channel={channel} order={order_id}")
        raise BusinessException(
            message="在线支付尚未开通，请改用线下对公。",
            code="PAYMENT_NOT_CONFIGURED",
        )


def get_payment_provider(channel: str) -> PaymentProvider:
    logger.debug(f"选择支付通道 | channel={channel}")
    if channel in ("alipay", "wechat"):
        return UnconfiguredOnlineProvider()
    return OfflinePaymentProvider()
