"""订阅计费：价目、线下挂账、在线结账占坑。验真/履约在 PaymentNotifyService。"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.order_repository import OrderRepository
from backend.repositories.payment_channel_credential_repository import (
    PaymentChannelCredentialRepository,
)
from backend.services.payment_provider import get_payment_provider
from backend.services.product_event_service import emit_product_event
from backend.services.quota_service import (
    BUYER_TENANT_ROLES,
    CHECKOUT_EMPTY_USER,
    CHECKOUT_PRODUCTS,
    CONTACT_ADMIN_UPGRADE,
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
CHECKOUT_PENDING_EXISTS_USER = "已有未完成的支付"
SUPERADMIN_NO_PAY_USER = "超管不能代企业支付"
PAID_PROCESSING_USER = "支付已到账，开通处理中"
UNPAID_USER = "支付未完成，套餐未开通"
CONFIRM_OFFLINE_ONLY_USER = "在线待支付不能线下确认"

# FR-92 事件名原样（蓝图 §5）：含 tenant_id + 档位名；无明文/密钥；失败不挡主路径。
OFFLINE_ORDER_SUBMITTED_EVENT = "offline_order_submitted"
OFFLINE_ORDER_CONFIRMED_EVENT = "offline_order_confirmed"

_PERIOD_DAYS = {"month": 30, "year": 365}


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
        is_platform_admin: bool = False,
    ) -> dict:
        """结账读面：不建单。两通道未配 → 收款通道未开通（200 空态）。"""
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
        can_pay = bool(configured)
        repo = OrderRepository(self.session)
        pending = await repo.get_open_for_product(int(tenant_id), product)
        latest = pending or await repo.get_latest_for_product(int(tenant_id), product)
        return {
            "product": product, "channels": channels,
            "empty_state": None if can_pay else CHECKOUT_EMPTY_USER,
            "can_pay": can_pay,
            "order_id": int(pending.id) if pending is not None else None,
            "amount_cents": await self._peek_amount(product),
            "notice": self._notice_for(latest),
        }

    @staticmethod
    def _notice_for(order: Optional[Order]) -> Optional[str]:
        if order is None:
            return None
        if order.status == "paid_pending_fulfillment":
            return PAID_PROCESSING_USER
        if order.status == "unpaid":
            return UNPAID_USER
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
        product: str, channel: str, actor_user_id: Optional[int] = None,
        is_platform_admin: bool = False,
    ) -> OrderOut:
        logger.info(
            f"创建结账 | tenant={tenant_id} role={actor_tenant_role} "
            f"product={product} channel={channel}"
        )
        self._assert_checkout_actor(is_platform_admin, tenant_id, actor_tenant_role)
        if product not in CHECKOUT_PRODUCTS or channel not in _ONLINE:
            raise BusinessException(message="没有这个商品。", code="CHECKOUT_UNKNOWN_PRODUCT")
        cred_repo = PaymentChannelCredentialRepository(self.session)
        configured = await cred_repo.configured_channels()
        if not configured:
            raise BusinessException(
                message=CHECKOUT_EMPTY_USER, code="BILLING_CHANNELS_UNCONFIGURED",
                status_code=422,
            )
        plan, amount, plan_name = await self._amount_snapshot(product)
        if channel not in configured:
            await self._fail_unconfigured(
                int(tenant_id), product, channel, amount, plan, actor_user_id, actor_tenant_role,
            )
        cred = await cred_repo.get_by_channel(channel)
        merchant = str(cred.merchant_no) if cred is not None else None
        return await self._insert_pending(
            int(tenant_id), product, channel, amount, plan, plan_name, merchant,
        )

    def _new_checkout_order(
        self, tenant_id: int, product: str, channel: str, amount: int,
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
                message=CHECKOUT_PENDING_EXISTS_USER, code="CHECKOUT_PENDING_EXISTS",
                status_code=409,
            )

    async def _insert_pending(
        self, tenant_id: int, product: str, channel: str, amount: int,
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
        self._assert_order_allowed(actor_tenant_role, payload.channel)
        plan = await self.session.get(Plan, payload.plan_id)
        if plan is None or not plan.is_public:
            raise NotFoundException("套餐")
        if int(plan.price_cents or 0) <= 0:
            raise BusinessException(message="免费档无需下单", code="ORDER_FREE_PLAN")
        order = Order(
            tenant_id=tenant_id,
            plan_id=plan.id,
            amount_cents=plan.price_cents,
            status="pending",
            channel="offline",
            idempotency_key=f"pending:{tenant_id}",
        )
        self.session.add(order)
        try:
            await self.session.flush()
        except IntegrityError:
            # GWT-50.15：单 pending 靠 idempotency_key 唯一约束兜底（非先查后插）。
            await self.session.rollback()
            raise BusinessException(
                message="已有待确认的升级申请", code="ORDER_PENDING_EXISTS",
            ) from None
        # 快照先于 commit（P-BE-01：commit 后访问过期 ORM 属性触发同步刷新）。
        order_id_snapshot = int(order.id)
        plan_name_snapshot = plan.name
        get_payment_provider(order.channel).collect(
            order_id=order_id_snapshot, amount_cents=int(order.amount_cents), channel=order.channel,
        )
        await self.session.commit()
        # GWT-92.1：进入待确认即上报（独立短会话，失败不挡主路径）；无明文/密钥。
        await emit_product_event(
            self.session, OFFLINE_ORDER_SUBMITTED_EVENT,
            tenant_id=tenant_id, actor_user_id=actor_user_id,
            role=actor_tenant_role,
            props={"order_id": order_id_snapshot, "plan_name": plan_name_snapshot},
        )
        await self.session.refresh(order)
        out = OrderOut.model_validate(order)
        out.plan_name = plan_name_snapshot
        return out

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
            .join(Plan, Order.plan_id == Plan.id)
            .join(Tenant, Order.tenant_id == Tenant.id)
            .where(Order.status == "pending")
            .order_by(Order.id.desc())
        )).all()
        return [self._to_out(order, plan_name, tenant_name=tenant_name)
                for order, plan_name, tenant_name in rows]

    async def confirm_paid(
        self, order_id: int, actor_user_id: Optional[int] = None,
    ) -> OrderOut:
        logger.info(f"确认收款 | order={order_id} actor={actor_user_id}")
        order = await self.session.get(Order, order_id)
        if order is None:
            raise NotFoundException("订单")
        if (order.product_code in CHECKOUT_PRODUCTS) or (order.channel in _ONLINE):
            raise BusinessException(
                message=CONFIRM_OFFLINE_ONLY_USER, code="ORDER_CONFIRM_OFFLINE_ONLY",
            )
        plan = await self.session.get(Plan, order.plan_id)
        if plan is None:
            raise BusinessException("套餐已下架")
        plan_name_snapshot = plan.name  # 快照先于 commit（P-BE-01）
        if order.status == "paid":
            # GWT-50.11：再确认 = no-op——保持 paid，不重放 _apply_plan，不重复上报事件。
            return self._to_out(order, plan_name_snapshot)
        tenant_id_snapshot = int(order.tenant_id) if order.tenant_id is not None else None
        order_id_snapshot = int(order.id)
        now = datetime.now(timezone.utc)
        order.status = "paid"
        order.paid_at = now
        # 单 pending 是「同一企业同一时刻」：确认后释放占位键（改为按单号），
        # 该企业此后可再提交新申请。T-01 冻结语义，不可回退。
        order.idempotency_key = f"paid:{order_id_snapshot}"
        await self._apply_plan(tenant_id_snapshot, plan, now)
        await self.session.commit()
        # GWT-92.2：仅在真实 pending→paid 流转时上报一次；失败不挡主路径。
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

    async def _apply_plan(
        self, tenant_id: int | None, plan: Plan, now: datetime, period_days: int | None = 0,
    ) -> None:
        if tenant_id is None:
            raise NotFoundException("租户")
        tenant = await self.session.get(Tenant, tenant_id)
        if tenant is None:
            raise NotFoundException("租户")
        if plan.quota_json:
            try:
                tenant.quota = json.loads(plan.quota_json)
            except (TypeError, ValueError):
                pass
        days = period_days if period_days is not None else _PERIOD_DAYS.get(plan.period, 30)
        if plan.price_cents == 0:
            tenant.expires_at = None
            end = None
        else:
            end = now + timedelta(days=days or 30)
            tenant.expires_at = end.replace(tzinfo=None)
        sub = (await self.session.execute(
            select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if sub is None:
            sub = TenantSubscription(tenant_id=tenant_id, plan_id=plan.id, status="active")
            self.session.add(sub)
        sub.plan_id = plan.id
        sub.status = "active"
        sub.current_period_end = end
