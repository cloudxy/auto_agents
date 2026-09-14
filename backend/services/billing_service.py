"""订阅计费：价目、线下挂账、在线结账占坑。验真/履约在 PaymentNotifyService。"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.order_repository import OrderRepository
from backend.repositories.payment_channel_credential_repository import (
    PaymentChannelCredentialRepository,
)
from backend.services.billing_fulfill import apply_plan_quota, fulfill_checkout_product
from backend.services.product_event_service import emit_product_event
from backend.services.quota_service import (
    BUYER_TENANT_ROLES,
    CHECKOUT_PENDING_EXISTS_USER,
    CHECKOUT_PRODUCTS,
    CHECKOUT_UNCONFIGURED_SUBMIT_USER,
    CONTACT_ADMIN_UPGRADE,
    ORDER_STORY_CLOSED_USER,
)
from config import settings
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.models.billing import Order, Plan, TenantSubscription
from platform_core.models.tenant import Tenant
from platform_core.schemas.billing import OrderCreate, OrderOut, PlanOut, SubscriptionOut

logger = get_logger("service.billing")

_PRODUCT_SLUG = {"plan_pro": "pro", "plan_enterprise": "enterprise"}
_ONLINE = frozenset({"alipay", "wechat"})
CHANNEL_UNCONFIGURED_USER = "该通道未开通"
SUPERADMIN_NO_PAY_USER = "超管不能代企业支付"
PENDING_NOTICE_USER = "待支付"
FULFILLED_NOTICE_USER = "已开通"

OFFLINE_ORDER_SUBMITTED_EVENT = "offline_order_submitted"
OFFLINE_ORDER_CONFIRMED_EVENT = "offline_order_confirmed"


class BillingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_public_plans(self) -> list[PlanOut]:
        logger.info("列出公开套餐")
        rows = (await self.session.execute(
            select(Plan).where(Plan.is_public == 1).order_by(Plan.price_cents.asc())
        )).scalars().all()
        return [PlanOut.model_validate(r) for r in rows]

    async def get_subscription(self, tenant_id: int) -> Optional[SubscriptionOut]:
        logger.info(f"读取订阅 | tenant={tenant_id}")
        row = (await self.session.execute(
            select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
        )).scalar_one_or_none()
        return SubscriptionOut.model_validate(row) if row else None

    async def preview_checkout(
        self, tenant_id: Optional[int], actor_tenant_role: Optional[str], product: str,
        is_platform_admin: bool = False, actor_user_id: Optional[int] = None,
        referrer_surface: str = "nav",
    ) -> dict:
        """结账读面：不建单。未配通道仍可见商品与提交入口。"""
        logger.info(
            f"打开结账 | tenant={tenant_id} role={actor_tenant_role} product={product}"
        )
        self._assert_checkout_actor(is_platform_admin, tenant_id, actor_tenant_role)
        if product not in CHECKOUT_PRODUCTS:
            raise BusinessException(message="没有这个商品。", code="CHECKOUT_UNKNOWN_PRODUCT")
        configured = await PaymentChannelCredentialRepository(self.session).configured_channels()
        channels = [
            {"channel": ch, "configured": ch in configured, "selectable": ch in configured}
            for ch in ("alipay", "wechat")
        ]
        repo = OrderRepository(self.session)
        pending = await repo.get_open_for_product(int(tenant_id), product)
        latest = pending or await repo.get_latest_for_product(int(tenant_id), product)
        await self._emit_checkout_started(
            int(tenant_id), product, referrer_surface, actor_user_id, actor_tenant_role,
        )
        return await self._preview_payload(
            product, channels, configured, pending, latest,
        )

    async def _emit_checkout_started(
        self, tenant_id: int, product: str, referrer: str,
        actor_user_id: Optional[int], role: Optional[str],
    ) -> None:
        logger.info(f"上报进入结账 | tenant={tenant_id} product={product}")
        surface = referrer if referrer in ("pricing", "usage", "nav") else "nav"
        await emit_product_event(
            self.session, "checkout_story_started",
            tenant_id=tenant_id, actor_user_id=actor_user_id, role=role,
            props={
                "tenant_id": tenant_id, "product": product,
                "surface": "checkout", "referrer_surface": surface,
            },
        )

    async def _preview_payload(
        self, product: str, channels: list, configured: set,
        pending: Optional[Order], latest: Optional[Order],
    ) -> dict:
        logger.info(f"组装结账预览 | product={product} pending={pending is not None}")
        pending_open = pending is not None
        wait_unconfigured = not configured
        show_gold = pending_open and wait_unconfigured
        gold = CHECKOUT_UNCONFIGURED_SUBMIT_USER
        return {
            "product": product, "channels": channels,
            "empty_state": gold if show_gold else None,
            "can_pay": not show_gold,
            "order_id": int(pending.id) if pending is not None else None,
            "amount_cents": await self._peek_amount(product),
            "notice": gold if show_gold else self._notice_for(latest),
        }

    @staticmethod
    def _notice_for(order: Optional[Order]) -> Optional[str]:
        if order is None:
            return None
        if order.status == "checkout_pending":
            return PENDING_NOTICE_USER
        if order.status in ("fulfilled", "paid"):
            return FULFILLED_NOTICE_USER
        return None

    def _assert_checkout_actor(
        self, is_platform_admin: bool, tenant_id: Optional[int], role: Optional[str],
    ) -> None:
        if is_platform_admin:
            raise BusinessException(message=SUPERADMIN_NO_PAY_USER, code="CHECKOUT_SUPERADMIN_FORBIDDEN")
        if tenant_id is None:
            raise BusinessException("需要租户上下文")
        if role not in BUYER_TENANT_ROLES:
            raise BusinessException(message=CONTACT_ADMIN_UPGRADE, code="ORDER_ROLE_NOT_ALLOWED")

    async def _peek_amount(self, product: str) -> Optional[int]:
        try:
            _plan, cents, _name = await self._amount_snapshot(product)
        except BusinessException:
            return None
        return cents

    async def _amount_snapshot(self, product: str) -> tuple[Optional[Plan], int, str]:
        logger.info(f"结账金额快照 | product={product}")
        if product == "relay":
            cents = int(settings.get("BILLING.RELAY_PRICE_CENTS") or 0)
            if cents <= 0:
                raise BusinessException(message="中转商品尚未标价", code="CHECKOUT_PRICE_MISSING")
            return None, cents, "中转"
        slug = _PRODUCT_SLUG.get(product)
        plan = (await self.session.execute(select(Plan).where(Plan.slug == slug))).scalar_one_or_none()
        if plan is None or int(plan.price_cents or 0) <= 0:
            raise BusinessException(message="商品尚未标价", code="CHECKOUT_PRICE_MISSING")
        return plan, int(plan.price_cents), str(plan.name)

    async def create_checkout(
        self, tenant_id: Optional[int], actor_tenant_role: Optional[str],
        product: str, channel: Optional[str] = None, actor_user_id: Optional[int] = None,
        is_platform_admin: bool = False,
    ) -> OrderOut:
        logger.info(
            f"创建结账 | tenant={tenant_id} role={actor_tenant_role} "
            f"product={product} channel={channel}"
        )
        self._assert_checkout_actor(is_platform_admin, tenant_id, actor_tenant_role)
        if product not in CHECKOUT_PRODUCTS:
            raise BusinessException(message="没有这个商品。", code="CHECKOUT_UNKNOWN_PRODUCT")
        if channel is not None and channel not in _ONLINE:
            raise BusinessException(message="没有这个商品。", code="CHECKOUT_UNKNOWN_PRODUCT")
        cred_repo = PaymentChannelCredentialRepository(self.session)
        configured = await cred_repo.configured_channels()
        plan, amount, plan_name = await self._amount_snapshot(product)
        use_channel = channel if channel in configured else None
        merchant = None
        if use_channel:
            cred = await cred_repo.get_by_channel(use_channel)
            merchant = str(cred.merchant_no) if cred is not None else None
        out = await self._insert_pending(
            int(tenant_id), product, use_channel, amount, plan, plan_name, merchant,
        )
        await self._emit_status(int(tenant_id), product, "pending", actor_user_id, actor_tenant_role)
        return out

    async def _emit_status(
        self, tenant_id: int, product: str, status: str,
        actor_user_id: Optional[int], role: Optional[str],
    ) -> None:
        logger.info(f"上报订单状态 | tenant={tenant_id} product={product} status={status}")
        await emit_product_event(
            self.session, "order_status_reached",
            tenant_id=tenant_id, actor_user_id=actor_user_id, role=role,
            props={"tenant_id": tenant_id, "product": product, "status": status},
        )

    def _new_checkout_order(
        self, tenant_id: int, product: str, channel: Optional[str], amount: int,
        plan: Optional[Plan], merchant: Optional[str],
    ) -> Order:
        order_no = uuid.uuid4().hex
        return Order(
            tenant_id=tenant_id,
            plan_id=int(plan.id) if plan is not None else None,
            amount_cents=amount,
            status="checkout_pending",
            channel=channel,
            product_code=product,
            order_no=order_no,
            idempotency_key=order_no,
            merchant_id_snapshot=merchant,
        )

    async def _raise_if_open_slot(self, tenant_id: int, product: str) -> None:
        existing = await OrderRepository(self.session).get_open_for_product(tenant_id, product)
        if existing is not None:
            raise BusinessException(
                message=CHECKOUT_PENDING_EXISTS_USER, code="ORDER_PENDING_EXISTS",
                status_code=409,
            )

    async def _insert_pending(
        self, tenant_id: int, product: str, channel: Optional[str], amount: int,
        plan: Optional[Plan], plan_name: str, merchant: Optional[str],
    ) -> OrderOut:
        order = self._new_checkout_order(tenant_id, product, channel, amount, plan, merchant)
        self.session.add(order)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            await self._raise_if_open_slot(tenant_id, product)
            raise
        await self.session.commit()
        await self.session.refresh(order)
        return self._to_out(order, plan_name)

    async def _fail_unconfigured(
        self, tenant_id: int, product: str, channel: str, amount: int,
        plan: Optional[Plan], actor_user_id: Optional[int], role: Optional[str],
    ) -> None:
        order = self._new_checkout_order(tenant_id, product, channel, amount, plan, None)
        order.fail_reason = "unconfigured"
        self.session.add(order)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            await self._raise_if_open_slot(tenant_id, product)
            raise
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        order.status = "unpaid"
        order.unpaid_at = now
        order_id = int(order.id)
        await self.session.commit()
        await emit_product_event(
            self.session, "payment_failed",
            tenant_id=tenant_id, actor_user_id=actor_user_id, role=role,
            props={"reason": "unconfigured", "channel": channel, "product": product},
        )
        raise BusinessException(
            message=CHANNEL_UNCONFIGURED_USER, code="BILLING_CHANNEL_UNCONFIGURED",
            status_code=422,
            data={"order_id": order_id, "status": "unpaid", "fail_reason": "unconfigured"},
        )

    def _assert_order_allowed(self, actor_tenant_role: Optional[str], channel: str) -> None:
        """下单前置拒绝：角色（GWT-50.7/50.8）与在线通道（GWT-50.5）。"""
        if actor_tenant_role not in ("owner", "admin"):
            # 经办/只读不产生订单；用户可见找管理员句，无 FORBIDDEN/QUOTA_EXCEEDED 内码。
            raise BusinessException(message="请联系企业管理员", code="ORDER_ROLE_NOT_ALLOWED")
        if channel in ("alipay", "wechat"):
            # 在线渠道零新行（含不产生 pending）；可见句不带 PAYMENT_NOT_CONFIGURED。
            raise BusinessException(
                message="在线支付尚未开通，请改用线下对公。", code="ORDER_ONLINE_UNAVAILABLE",
            )

    async def create_order(
        self, tenant_id: int, actor_tenant_role: Optional[str], payload: OrderCreate,
        actor_user_id: Optional[int] = None,
    ) -> OrderOut:
        logger.info(
            f"创建订单 | tenant={tenant_id} role={actor_tenant_role} "
            f"plan={payload.plan_id} channel={payload.channel}"
        )
        raise BusinessException(
            message=ORDER_STORY_CLOSED_USER, code="ORDER_STORY_CLOSED", status_code=422,
        )

    async def list_orders(self, tenant_id: int) -> list[OrderOut]:
        logger.info(f"列出订单 | tenant={tenant_id}")
        rows = await OrderRepository(self.session).list_tenant_with_plan_name(tenant_id)
        outs: list[OrderOut] = []
        for order, plan_name in rows:
            name = plan_name or ("中转" if order.product_code == "relay" else "")
            outs.append(self._to_out(order, name))
        return outs

    async def list_pending_orders(self) -> list[OrderOut]:
        logger.info("列出待确认收款订单")
        rows = (await self.session.execute(
            select(Order, Plan.name, Tenant.name)
            .outerjoin(Plan, Order.plan_id == Plan.id)
            .join(Tenant, Order.tenant_id == Tenant.id)
            .where(Order.status.in_(("checkout_pending", "pending")))
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

    async def _plan_name_of(self, order: Order) -> str:
        if order.plan_id is None:
            return "中转" if order.product_code == "relay" else ""
        plan = await self.session.get(Plan, order.plan_id)
        return str(plan.name) if plan is not None else ""

    async def _confirm_checkout(self, order: Order, actor_user_id: Optional[int]) -> OrderOut:
        logger.info(f"确认结账单 | order={order.id} product={order.product_code}")
        product = str(order.product_code or "")
        _plan, display, plan_name = await self._amount_snapshot(product)
        if int(order.amount_cents) != int(display):
            raise BusinessException(
                message="确认金额与结账页不一致", code="CONFIRM_AMOUNT_MISMATCH",
                status_code=422,
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
                message="确认金额与结账页不一致", code="CONFIRM_AMOUNT_MISMATCH",
                status_code=422,
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

    @staticmethod
    def _to_out(order: Order, plan_name: str, *, tenant_name: Optional[str] = None) -> OrderOut:
        out = OrderOut.model_validate(order)
        out.plan_name = plan_name
        out.tenant_name = tenant_name
        return out

    async def attach_free_plan(self, tenant_id: int) -> None:
        logger.info(f"挂接免费档 | tenant={tenant_id}")
        plan = (await self.session.execute(
            select(Plan).where(Plan.slug == "free")
        )).scalar_one_or_none()
        if plan is None:
            return
        await self._apply_plan(tenant_id, plan, datetime.now(timezone.utc), period_days=None)
        await self.session.flush()
        try:
            from backend.services.litellm.admin_service import LiteLlmAdminService

            await LiteLlmAdminService().ensure_tenant_key(tenant_id)
        except Exception as e:  # noqa: BLE001 中转站未启用不阻断注册
            logger.warning(f"LiteLLM 虚拟键签发失败（忽略）: tenant={tenant_id} err={e}")

    async def _apply_plan(
        self, tenant_id: int | None, plan: Plan, now: datetime, period_days: int | None = 0,
    ) -> None:
        await apply_plan_quota(
            self.session, tenant_id, plan, now, period_days=period_days,
        )
