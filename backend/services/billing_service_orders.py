"""订单生命周期（BillingService 的后台面）：确认收款、取消、超时关闭、补偿履约、平台开通。

审计 BUG-24 / BUG-25 / 决策 D17。以 mixin 挂在 BillingService 上，方法名与签名不变；
依赖宿主提供 session 与 _to_out / _plan_name_of / _emit_status / _amount_snapshot /
_new_checkout_order / _apply_plan。
"""
import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.order_repository import OrderRepository
from backend.services.billing_fulfill import fulfill_checkout_product
from backend.services.billing_service_common import (
    _ONLINE, _PRODUCT_SLUG, _billing_cfg, _naive_utc, amount_signature,
)
from backend.services.product_event_service import emit_product_event
from backend.services.quota_service import (
    BUYER_TENANT_ROLES,
    CHECKOUT_PRODUCTS,
    CONTACT_ADMIN_UPGRADE,
)
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.timeutil import utcnow
from platform_core.models.billing import Order, Plan
from platform_core.models.tenant import Tenant
from platform_core.schemas.billing import OrderOut

logger = get_logger("service.billing")

OFFLINE_ORDER_SUBMITTED_EVENT = "offline_order_submitted"
OFFLINE_ORDER_CONFIRMED_EVENT = "offline_order_confirmed"
ORDER_CANCELLED_USER = "订单已取消"
ORDER_NOT_CANCELLABLE_USER = "这笔订单已付款或已关闭，不能取消"
ORDER_NOT_CONFIRMABLE_USER = "这笔订单已关闭，不能确认收款"

# 待支付超时（审计 BUG-24）：在线单须长于通道支付窗口（支付宝默认 90 分钟），线下对公单
# 等人工确认收款，窗口按天计；超时单在下次打开结账 / 下单 / 超管列表时惰性关闭
_DEFAULT_ONLINE_TTL_MINUTES = 24 * 60
_DEFAULT_OFFLINE_TTL_HOURS = 7 * 24


class BillingOrderOpsMixin:
    """BillingService 订单生命周期方法（宿主须提供 session 及上文列出的私有方法）"""

    session: AsyncSession

    async def list_pending_orders(self) -> list[OrderOut]:
        """超管待处理订单：待确认收款 + 已付款待开通 + 超时 / 取消后才到账的成功通知

        审计 BUG-25：已付款待开通（履约失败）与迟到到账的单原先超管看不到，钱收了权益没开。
        """
        from sqlalchemy import and_, or_

        logger.info("列出待处理订单")
        await self._expire_stale_open_orders()
        rows = (await self.session.execute(
            select(Order, Plan.name, Tenant.name)
            .outerjoin(Plan, Order.plan_id == Plan.id)
            .join(Tenant, Order.tenant_id == Tenant.id)
            .where(or_(
                Order.status.in_(("checkout_pending", "pending", "paid_pending_fulfillment")),
                and_(Order.status == "unpaid", Order.late_notify_at.is_not(None)),
            ))
            .order_by(Order.id.desc())
        )).all()
        outs = []
        for order, plan_name, tenant_name in rows:
            name = plan_name or ("中转" if order.product_code == "relay" else "")
            outs.append(self._to_out(order, name, tenant_name=tenant_name))
        return outs

    async def confirm_paid(
        self, order_id: int, actor_user_id: Optional[int] = None,
        expected_order_id: Optional[int] = None,
    ) -> OrderOut:
        logger.info(f"确认收款 | order={order_id} actor={actor_user_id}")
        if expected_order_id is not None and int(expected_order_id) != int(order_id):
            raise BusinessException(
                message="确认单与本笔不符", code="CONFIRM_ORDER_MISMATCH", status_code=422,
            )
        order = await self.session.get(Order, order_id)
        if order is None:
            raise NotFoundException("订单")
        if order.status in ("fulfilled", "paid"):
            return await self._confirm_noop(order)
        if str(order.product_code or "") in CHECKOUT_PRODUCTS or order.status == "checkout_pending":
            return await self._confirm_checkout(order, actor_user_id)
        return await self._confirm_legacy_offline(order, actor_user_id)

    async def _confirm_noop(self, order: Order) -> OrderOut:
        logger.info(f"再确认 no-op | order={order.id} status={order.status}")
        name = await self._plan_name_of(order)
        return self._to_out(order, name)

    async def _confirm_checkout(self, order: Order, actor_user_id: Optional[int]) -> OrderOut:
        logger.info(f"确认结账单 | order={order.id} product={order.product_code}")
        product = str(order.product_code or "")
        display = await self._verified_snapshot_amount(order, product)
        plan_name = await self._plan_name_of(order)
        if order.status not in ("checkout_pending",):
            raise BusinessException(
                message=ORDER_NOT_CONFIRMABLE_USER, code="ORDER_NOT_CONFIRMABLE", status_code=409,
            )
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        oid = int(order.id)
        tid = int(order.tenant_id) if order.tenant_id is not None else None
        rows = await OrderRepository(self.session).cas_confirm_checkout(oid, int(display), now)
        if rows == 0:
            fresh = await OrderRepository(self.session).get_fresh(oid)
            if fresh is not None and fresh.status == "fulfilled":
                return self._to_out(fresh, plan_name)
            raise BusinessException(
                message=ORDER_NOT_CONFIRMABLE_USER, code="ORDER_NOT_CONFIRMABLE", status_code=409,
            )
        fresh = await OrderRepository(self.session).get_fresh(oid)
        await fulfill_checkout_product(self.session, fresh or order, now)
        await self.session.commit()
        await self._emit_status(tid or 0, product, "fulfilled", actor_user_id, None)
        await emit_product_event(
            self.session, OFFLINE_ORDER_CONFIRMED_EVENT,
            tenant_id=tid, actor_user_id=actor_user_id,
            props={"order_id": oid, "plan_name": plan_name, "product": product},
        )
        out_row = await OrderRepository(self.session).get_fresh(oid)
        return self._to_out(out_row or order, plan_name)

    async def _verified_snapshot_amount(self, order: Order, product: str) -> int:
        """确认金额以下单快照为准（审计 BUG-24）：有签名则验签，签名不符视为篡改；
        存量无签名行回退旧口径（与现价比对）"""
        sig = str(getattr(order, "amount_sig", "") or "")
        if sig:
            expected = amount_signature(str(order.order_no or ""), product, int(order.amount_cents))
            if not hmac.compare_digest(sig, expected):
                logger.warning(f"订单金额快照签名不符 | order={order.id}")
                raise BusinessException(
                    message="确认金额与结账页不一致", code="CONFIRM_AMOUNT_MISMATCH", status_code=422,
                )
            return int(order.amount_cents)
        _plan, display, _name = await self._amount_snapshot(product)
        if int(order.amount_cents) != int(display):
            raise BusinessException(
                message="确认金额与结账页不一致", code="CONFIRM_AMOUNT_MISMATCH", status_code=422,
            )
        return int(display)

    # ---------------- 取消 / 超时 / 补偿（审计 BUG-24、BUG-25） ----------------

    async def cancel_checkout(
        self, order_id: int, tenant_id: Optional[int], actor_tenant_role: Optional[str],
        actor_user_id: Optional[int] = None,
    ) -> OrderOut:
        """买方取消本企业待支付单（只能取消 checkout_pending；已付款 / 已关闭 409）"""
        logger.info(f"取消待支付 | order={order_id} tenant={tenant_id} role={actor_tenant_role}")
        if tenant_id is None:
            raise BusinessException("需要租户上下文")
        if actor_tenant_role not in BUYER_TENANT_ROLES:
            raise BusinessException(message=CONTACT_ADMIN_UPGRADE, code="ORDER_ROLE_NOT_ALLOWED")
        repo = OrderRepository(self.session)
        order = await repo.get_fresh(order_id)
        if order is None or int(order.tenant_id) != int(tenant_id):
            raise NotFoundException("订单")
        product = str(order.product_code or "")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        rows = await repo.cas_mark_unpaid(int(order.id), now, "cancel")
        if rows != 1:
            await self.session.rollback()
            raise BusinessException(
                message=ORDER_NOT_CANCELLABLE_USER, code="ORDER_NOT_CANCELLABLE", status_code=409,
            )
        await self.session.commit()
        await self._emit_status(int(tenant_id), product, "cancelled", actor_user_id, actor_tenant_role)
        fresh = await repo.get_fresh(order_id)
        return self._to_out(fresh or order, await self._plan_name_of(fresh or order))

    @staticmethod
    def _ttl_for(order: Order) -> timedelta:
        if order.channel in _ONLINE:
            minutes = int(_billing_cfg("ONLINE_CHECKOUT_TTL_MINUTES", _DEFAULT_ONLINE_TTL_MINUTES))
            return timedelta(minutes=max(minutes, 120))
        hours = int(_billing_cfg("OFFLINE_CHECKOUT_TTL_HOURS", _DEFAULT_OFFLINE_TTL_HOURS))
        return timedelta(hours=max(hours, 1))

    def _is_stale(self, order: Order, now: datetime) -> bool:
        created = _naive_utc(getattr(order, "created_at", None))
        if created is None or order.status != "checkout_pending":
            return False
        # 库时区与应用时区可能不同（SQLite UTC / MySQL 会话时区），留 14 小时余量（覆盖任意时区偏差），宁晚勿早
        return now - created > self._ttl_for(order) + timedelta(hours=14)

    async def _expire_if_stale(self, order: Optional[Order]) -> Optional[Order]:
        """超时的待支付单惰性关闭为 unpaid(timeout)；返回仍有效的待支付单或 None"""
        if order is None:
            return None
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if not self._is_stale(order, now):
            return order
        logger.info(f"待支付超时关闭 | order={order.id}")
        rows = await OrderRepository(self.session).cas_mark_unpaid(int(order.id), now, "timeout")
        await self.session.commit()
        return None if rows == 1 else await OrderRepository(self.session).get_fresh(int(order.id))

    async def _expire_stale_open_orders(self) -> int:
        """超管列表前批量关闭超时待支付单"""
        rows = (await self.session.execute(
            select(Order).where(Order.status == "checkout_pending")
        )).scalars().all()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        stale = [o for o in rows if self._is_stale(o, now)]
        repo = OrderRepository(self.session)
        for order in stale:
            await repo.cas_mark_unpaid(int(order.id), now, "timeout")
        if stale:
            await self.session.commit()
            logger.info(f"批量关闭超时待支付 | n={len(stale)}")
        return len(stale)

    async def retry_fulfillment(self, order_id: int) -> OrderOut:
        """超管补偿：已付款待开通的单重新履约（审计 BUG-25）"""
        from backend.services.payment_notify_service import PaymentNotifyService

        logger.info(f"补偿履约 | order={order_id}")
        order = await OrderRepository(self.session).get_fresh(order_id)
        if order is None:
            raise NotFoundException("订单")
        if order.status != "paid_pending_fulfillment":
            raise BusinessException(
                message="只有「已付款待开通」的订单可以重新开通", code="ORDER_NOT_RETRYABLE",
                status_code=409,
            )
        ok = await PaymentNotifyService(self.session).fulfill_pending(order_id)
        fresh = await OrderRepository(self.session).get_fresh(order_id)
        if not ok:
            raise BusinessException(
                message="开通仍未成功，请检查套餐配置后重试", code="FULFILLMENT_FAILED",
                status_code=409,
            )
        return self._to_out(fresh or order, await self._plan_name_of(fresh or order))

    async def _confirm_legacy_offline(
        self, order: Order, actor_user_id: Optional[int],
    ) -> OrderOut:
        logger.info(f"确认旧线下单 | order={order.id}")
        plan = await self.session.get(Plan, order.plan_id)
        if plan is None:
            raise BusinessException("套餐已下架")
        plan_name_snapshot = plan.name
        tenant_id_snapshot = int(order.tenant_id) if order.tenant_id is not None else None
        order_id_snapshot = int(order.id)
        now = datetime.now(timezone.utc)
        order.status = "paid"
        order.paid_at = now
        order.idempotency_key = f"paid:{order_id_snapshot}"
        await self._apply_plan(tenant_id_snapshot, plan, now)
        await self.session.commit()
        await emit_product_event(
            self.session, OFFLINE_ORDER_CONFIRMED_EVENT,
            tenant_id=tenant_id_snapshot, actor_user_id=actor_user_id,
            props={"order_id": order_id_snapshot, "plan_name": plan_name_snapshot},
        )
        await self.session.refresh(order)
        return self._to_out(order, plan_name_snapshot)

    async def grant_plan(
        self, tenant_id: int, product: str, amount_cents: int, periods: int,
        note: str = "", actor_user_id: Optional[int] = None,
    ) -> OrderOut:
        """平台为定制客户开通套餐（决策 D17：企业档走销售，成交后由平台开通）。

        记一笔「线下已收款、已开通」的订单（合同金额 + 期数），再走与自助结账同一条履约路径
        （订阅、配额、企业档附带的中转 SKU），收入与开通记录都可追溯。
        """
        logger.info(f"平台开通套餐 | tenant={tenant_id} product={product} periods={periods} amount={amount_cents}")
        slug = _PRODUCT_SLUG.get(product)
        if slug is None:
            raise BusinessException(message="没有这个套餐。", code="CHECKOUT_UNKNOWN_PRODUCT")
        if await self.session.get(Tenant, tenant_id) is None:
            raise NotFoundException("租户")
        plan = (await self.session.execute(select(Plan).where(Plan.slug == slug))).scalar_one_or_none()
        if plan is None:
            raise BusinessException(message="套餐已下架或不存在", code="FULFILLMENT_PLAN_MISSING", status_code=409)
        now = utcnow()
        order = self._new_checkout_order(tenant_id, product, "offline", int(amount_cents), plan, None)
        order.status = "fulfilled"
        order.paid_at = now
        order.fulfilled_at = now
        order.idempotency_key = f"grant:{order.order_no}"
        self.session.add(order)
        await self.session.flush()
        oid = int(order.id)
        await fulfill_checkout_product(self.session, order, now, periods=periods)
        await self.session.commit()
        await self._emit_status(tenant_id, product, "fulfilled", actor_user_id, None)
        await emit_product_event(
            self.session, "sales_plan_granted", tenant_id=tenant_id, actor_user_id=actor_user_id,
            props={"order_id": oid, "product": product, "periods": int(periods),
                   "amount_cents": int(amount_cents), "note": (note or "")[:200]},
        )
        fresh = await OrderRepository(self.session).get_fresh(oid)
        return self._to_out(fresh or order, str(plan.name))
