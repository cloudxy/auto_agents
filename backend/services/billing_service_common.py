"""订阅计费共用底座：BILLING 配置读取、商品码映射、下单金额快照签名、时间归一。

billing_service（结账）与 billing_service_orders（确认 / 取消 / 超时 / 补偿）共用，
单独成模块以免两者循环导入；billing_service 原样 re-export 这些名字。
"""
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Optional

from config import settings
from platform_core.logger import get_logger

logger = get_logger("service.billing")

_PRODUCT_SLUG = {"plan_pro": "pro", "plan_enterprise": "enterprise"}
_ONLINE = frozenset({"alipay", "wechat"})


def _billing_cfg(key: str, default=None):
    """读 BILLING 段子键（先取段再取键：避免点路径在 Dynaconf 内部带 parent 递归）"""
    section = settings.get("BILLING") or {}
    try:
        value = section.get(key)
    except AttributeError:
        value = None
    return default if value is None else value


def _order_sign_key() -> bytes:
    raw = _billing_cfg("ORDER_SIGN_KEY")
    if not raw:
        from backend.utils.auth import SECRET_KEY as raw
    return hashlib.sha256(f"order-amount:{raw}".encode()).digest()


def amount_signature(order_no: str, product: str, amount_cents: int) -> str:
    """下单金额快照签名（审计 BUG-24 / GWT-M31.4 [SEC-3]，迁移 052）"""
    logger.debug(f"订单金额签名 | order_no={order_no} product={product}")
    msg = f"{order_no}|{product}|{int(amount_cents)}".encode()
    return hmac.new(_order_sign_key(), msg, hashlib.sha256).hexdigest()


def _naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value
