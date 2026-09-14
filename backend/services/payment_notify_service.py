"""通道通知验真后履约（FR-U33/U34/U38）。伪造/四要素不符不开通。"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.order_repository import OrderRepository
from backend.repositories.payment_channel_credential_repository import (
    PaymentChannelCredentialRepository,
)
from backend.services.channel_notify_auth import mac_matches
from backend.services.llm_secret_vault import LlmSecretVault
from backend.services.product_event_service import emit_product_event
from platform_core.logger import get_logger
from platform_core.models.billing import Order
from platform_core.schemas.billing import ChannelNotifyIn

logger = get_logger("service.payment_notify")

_ONLINE = frozenset({"alipay", "wechat"})
_FAIL = frozenset({"cancel", "timeout", "channel_error"})
_OK = "success"


def _utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PaymentNotifyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.orders = OrderRepository(session)
        self.creds = PaymentChannelCredentialRepository(session)

    async def handle(self, channel: str, payload: ChannelNotifyIn) -> None:
        logger.info(f"处理通道通知 | channel={channel} order_no={payload.order_no}")
        if channel not in _ONLINE:
            return
        order = await self._verify(channel, payload)
        if order is None:
            return
        status = str(payload.trade_status or "")
        oid = int(order.id)
        if status == _OK:
            await self._on_success(order, payload)
            return
        if status in _FAIL:
            await self._on_fail(oid, int(order.tenant_id), str(order.product_code or ""),
                                channel, status)

    async def _verify(self, channel: str, payload: ChannelNotifyIn) -> Optional[Order]:
        logger.info(f"验真通道通知 | channel={channel} order_no={payload.order_no}")
        fields = self._fields(payload)
        if fields is None:
            logger.info("通道通知缺字段或非闭集状态，保持未开通")
            return None
        secret, merchant = await self._current_secret(channel)
        if not secret or not merchant:
            logger.info(f"通道无当前凭据，保持未开通 | channel={channel}")
            return None
        if not mac_matches(secret, str(payload.sign or ""), channel=channel, **fields):
            logger.info("通道通知未视为真通知，保持未开通")
            return None
        order = await self.orders.get_by_order_no(fields["order_no"])
        if order is None:
            logger.info("通道通知订单号无对应待支付，保持未开通")
            return None
        if not self._four_match(order, channel, merchant, fields):
            return None
        return order

    def _fields(self, payload: ChannelNotifyIn) -> Optional[dict]:
        order_no = str(payload.order_no or "").strip()
        merchant_no = str(payload.merchant_no or "").strip()
        status = str(payload.trade_status or "").strip()
        sign = str(payload.sign or "").strip()
        if not order_no or not merchant_no or payload.amount_cents is None or not sign:
            return None
        if status != _OK and status not in _FAIL:
            return None
        return {
            "order_no": order_no,
            "merchant_no": merchant_no,
            "amount_cents": int(payload.amount_cents),
            "trade_status": status,
        }

    async def _current_secret(self, channel: str) -> tuple[str, str]:
        logger.info(f"解密当前通道凭据 | channel={channel}")
        row = await self.creds.get_by_channel(channel)
        if row is None:
            return "", ""
        plain = LlmSecretVault.decrypt_api_key(str(row.secrets_encrypted or ""))
        return plain, str(row.merchant_no or "")

    def _four_match(self, order: Order, channel: str, merchant: str, fields: dict) -> bool:
        logger.info(f"核对商户金额订单号 | order={order.id}")
        if str(order.channel) != channel:
            logger.info("通道与单据不一致，保持未开通")
            return False
        if str(order.order_no or "") != fields["order_no"]:
            logger.info("订单号不符，保持未开通")
            return False
        snapshot = str(order.merchant_id_snapshot or "")
        if fields["merchant_no"] != snapshot or fields["merchant_no"] != merchant:
            logger.info("商户不符，保持未开通")
            return False
        if int(order.amount_cents) != int(fields["amount_cents"]):
            logger.info("金额不符，保持未开通")
            return False
        return True

    async def _on_success(self, order: Order, payload: ChannelNotifyIn) -> None:
        logger.info(f"验真通过待履约 | order={order.id}")
        oid = int(order.id)
        tid = int(order.tenant_id)
        product = str(order.product_code or "")
        channel = str(order.channel)
        trade_no = str(payload.channel_trade_no or "").strip() or None
        now = _utc_naive()
        rows = await self.orders.cas_mark_verified(oid, now, trade_no)
        await self.session.commit()
        self.session.expire_all()
        if rows == 1:
            await self._emit_ok(tid, channel, product)
            await self._fulfill(oid)
            return
        await self._success_when_cas_miss(oid, now)

    async def _success_when_cas_miss(self, oid: int, now: datetime) -> None:
        current = await self.orders.get_fresh(oid)
        if current is None:
            return
        if current.status == "unpaid":
            await self.orders.mark_late_notify(oid, now)
            await self.session.commit()
            logger.info(f"迟到成功通知，保持 unpaid | order={oid}")
            return
        if current.status == "fulfilled":
            await self.orders.mark_late_notify(oid, now)
            await self.session.commit()
            logger.info(f"迟到成功通知，保持已开通 | order={oid}")
            return
        if current.status == "paid_pending_fulfillment":
            await self._fulfill(oid)

    async def _on_fail(
        self, oid: int, tid: int, product: str, channel: str, reason: str,
    ) -> None:
        logger.info(f"通道失败通知 | order={oid} reason={reason}")
        now = _utc_naive()
        rows = await self.orders.cas_mark_unpaid(oid, now, reason)
        await self.session.commit()
        if rows != 1:
            return
        await emit_product_event(
            self.session, "payment_failed", tenant_id=tid,
            props={"reason": reason, "channel": channel, "product": product,
                   "tenant_id": tid},
        )

    async def _emit_ok(self, tid: int, channel: str, product: str) -> None:
        logger.info(f"上报 payment_succeeded | tenant={tid} product={product}")
        await emit_product_event(
            self.session, "payment_succeeded", tenant_id=tid,
            props={"channel": channel, "product": product, "tenant_id": tid},
        )

    async def _fulfill(self, order_id: int) -> None:
        logger.info(f"开通履约 | order={order_id}")
        order = await self.orders.get_fresh(order_id)
        if order is None or order.status != "paid_pending_fulfillment":
            logger.info(f"开通跳过非处理中单据 | order={order_id} status={getattr(order, 'status', None)}")
            return
        now = datetime.now(timezone.utc)
        await self._fulfill_product(order, now)
        rows = await self.orders.cas_mark_fulfilled(order_id, _utc_naive())
        if rows == 0:
            await self.session.rollback()
            logger.info(f"开通 CAS 0 行，回滚履约 | order={order_id}")
            return
        await self.session.commit()

    async def _fulfill_product(self, order: Order, now: datetime) -> None:
        from backend.services.billing_fulfill import fulfill_checkout_product
        await fulfill_checkout_product(self.session, order, now)
