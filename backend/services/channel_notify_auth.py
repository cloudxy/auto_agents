"""通道通知「视为通道侧真通知」的校验口（实现细节，不对用户命名算法）。"""
import hashlib
import hmac

from platform_core.logger import get_logger

logger = get_logger("service.payment_notify")


def notify_mac(
    secret: str,
    *,
    channel: str,
    order_no: str,
    merchant_no: str,
    amount_cents: int,
    trade_status: str,
) -> str:
    """用当前通道密钥对通知字段做校验码。测试可构造缺校验的伪造报文。"""
    logger.debug(f"通道通知校验码 | channel={channel}")
    msg = f"{channel}|{order_no}|{merchant_no}|{int(amount_cents)}|{trade_status}"
    return hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()


def mac_matches(
    secret: str,
    provided: str,
    *,
    channel: str,
    order_no: str,
    merchant_no: str,
    amount_cents: int,
    trade_status: str,
) -> bool:
    logger.debug(f"比对通道通知校验 | channel={channel}")
    if not secret or not provided:
        return False
    expected = notify_mac(
        secret,
        channel=channel,
        order_no=order_no,
        merchant_no=merchant_no,
        amount_cents=amount_cents,
        trade_status=trade_status,
    )
    return hmac.compare_digest(expected, provided)
