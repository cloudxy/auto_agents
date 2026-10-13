"""订阅计费：价目、线下挂账、在线结账（支付宝/微信真实网关）。验真/履约在
PaymentNotifyService。

订单生命周期（确认收款 / 取消 / 超时 / 补偿 / 平台开通）在 billing_service_orders
（BillingOrderOpsMixin）；BILLING 配置读取与金额快照签名在 billing_service_common。
"""
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
from backend.services.billing_fulfill import apply_plan_quota
from backend.services.billing_service_common import (
    _ONLINE, _PRODUCT_SLUG, _billing_cfg, _naive_utc, amount_signature,
)
from backend.services.billing_service_orders import BillingOrderOpsMixin
from backend.services.billing_service_orders import (  # noqa: F401 — 拆分后原路 re-export
    OFFLINE_ORDER_CONFIRMED_EVENT, OFFLINE_ORDER_SUBMITTED_EVENT, ORDER_CANCELLED_USER,
    ORDER_NOT_CANCELLABLE_USER, ORDER_NOT_CONFIRMABLE_USER,
)
from backend.services.payment_provider import create_payment_intent
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
from platform_core.timeutil import utcnow
from platform_core.models.billing import Order, Plan, TenantSubscription
from platform_core.schemas.billing import OrderCreate, OrderOut, PlanOut, SubscriptionOut

logger = get_logger("service.billing")

CHANNEL_UNCONFIGURED_USER = "该通道未开通"
SUPERADMIN_NO_PAY_USER = "超管不能代企业支付"
PENDING_NOTICE_USER = "待支付"
FULFILLED_NOTICE_USER = "已开通"


def _sales_led_slugs() -> set[str]:
    """决策 D17：按需定制、走「联系我们」的套餐 slug"""
    raw = _billing_cfg("SALES_LED_PLANS", ["enterprise"]) or []
    return {str(x) for x in raw}


class BillingService(BillingOrderOpsMixin):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_public_plans(self) -> list[PlanOut]:
        logger.info("列出公开套餐")
        rows = (await self.session.execute(
            select(Plan).where(Plan.is_public == 1).order_by(Plan.price_cents.asc())
        )).scalars().all()
        sales_led = _sales_led_slugs()
        return [PlanOut.model_validate(r).model_copy(update={"sales_led": r.slug in sales_led}) for r in rows]

    async def get_subscription(self, tenant_id: int) -> Optional[SubscriptionOut]:
        logger.info(f"读取订阅 | tenant={tenant_id}")
        row = (await self.session.execute(
            select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if row is None:
            return None
        out = SubscriptionOut.model_validate(row)
        plan = await self.session.get(Plan, row.plan_id)
        end = _naive_utc(row.current_period_end)
        grace_until = end + timedelta(days=int(_billing_cfg("GRACE_DAYS", 3))) if end is not None else None
        return out.model_copy(update={
            "plan_slug": getattr(plan, "slug", None),
            "plan_name": getattr(plan, "name", None),
            "grace_until": grace_until,
            "in_grace": bool(end is not None and end <= utcnow() < grace_until),
        })

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
        await self._assert_purchasable(int(tenant_id), product)
        configured = await PaymentChannelCredentialRepository(self.session).configured_channels()
        channels = [
            {"channel": ch, "configured": ch in configured, "selectable": ch in configured}
            for ch in ("alipay", "wechat")
        ]
        repo = OrderRepository(self.session)
        pending = await self._expire_if_stale(await repo.get_open_for_product(int(tenant_id), product))
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
            # 策略性拒绝用 403（审计 BUG-27）；前端对超管不展示结账入口
            raise BusinessException(
                message=SUPERADMIN_NO_PAY_USER, code="CHECKOUT_SUPERADMIN_FORBIDDEN", status_code=403,
            )
        if tenant_id is None:
            raise BusinessException("需要租户上下文")
        if role not in BUYER_TENANT_ROLES:
            raise BusinessException(message=CONTACT_ADMIN_UPGRADE, code="ORDER_ROLE_NOT_ALLOWED")

    async def _assert_purchasable(self, tenant_id: int, product: str) -> None:
        """自助结账闸：
        - 决策 D17：按需定制的套餐（企业档）走「联系我们」，不能自助结账；
        - 决策 D22：高档有效期内不能自助买低档——到期后自动转免费档，届时再买。
        """
        slug = _PRODUCT_SLUG.get(product)
        if slug is None:
            return  # 中转等非套餐商品
        if slug in _sales_led_slugs():
            from backend.services.ops_contact_service import public_contact

            email = public_contact().get("contact_email") or ""
            raise BusinessException(
                message=f"该套餐按需定制，请联系我们{('：' + email) if email else ''}。",
                code="PLAN_SALES_LED", status_code=409,
            )
        sub = (await self.session.execute(
            select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
        )).scalar_one_or_none()
        end = _naive_utc(getattr(sub, "current_period_end", None)) if sub is not None else None
        if sub is None or sub.status != "active" or end is None or end <= utcnow():
            return
        current = await self.session.get(Plan, sub.plan_id)
        target = (await self.session.execute(select(Plan).where(Plan.slug == slug))).scalar_one_or_none()
        if current is None or target is None or int(target.price_cents or 0) >= int(current.price_cents or 0):
            return
        raise BusinessException(
            message=(f"当前{current.name}有效期至 {end:%Y-%m-%d}，到期后自动转为免费档，届时可购买{target.name}；"
                     "如需提前调整请联系我们。"),
            code="SUBSCRIPTION_DOWNGRADE_AT_PERIOD_END", status_code=409,
        )

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
        await self._assert_purchasable(int(tenant_id), product)
        cred_repo = PaymentChannelCredentialRepository(self.session)
        configured = await cred_repo.configured_channels()
        plan, amount, plan_name = await self._amount_snapshot(product)
        # 超时的待支付单先关闭，免得一企一商品占坑把新下单挡死（审计 BUG-24）
        await self._expire_if_stale(
            await OrderRepository(self.session).get_open_for_product(int(tenant_id), product))
        use_channel = channel if channel in configured else None
        merchant = None
        if use_channel:
            cred = await cred_repo.get_by_channel(use_channel)
            merchant = str(cred.merchant_no) if cred is not None else None
        out = await self._insert_pending(
            int(tenant_id), product, use_channel, amount, plan, plan_name, merchant,
        )
        if use_channel:
            await self._attach_online_intent(out, use_channel, amount, plan_name)
        await self._emit_status(int(tenant_id), product, "pending", actor_user_id, actor_tenant_role)
        return out

    async def _attach_online_intent(
        self, out: OrderOut, channel: str, amount_cents: int, subject: str,
    ) -> None:
        """商户凭据已配置时尝试拿一个真实收银台链接/二维码；失败只记日志不阻断
        下单——订单已经落库为 checkout_pending，照旧能走人工确认收款兜底。"""
        try:
            intent = await create_payment_intent(
                self.session, channel=channel, order_no=str(out.order_no),
                amount_cents=amount_cents, subject=subject,
            )
        except BusinessException as exc:
            logger.warning(f"在线支付意图创建失败，回退人工确认收款 | order={out.id} err={exc}")
            return
        out.pay_url = intent.checkout_url
        out.qr_code_url = intent.qr_code_url
        out.qr_code_image = intent.qr_code_image

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
            amount_sig=amount_signature(order_no, product, amount),
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

    async def regenerate_pay_intent(self, order_id: int, tenant_id: int) -> OrderOut:
        """按需重取在线支付链接/二维码（未持久化，每次现取现签——支付宝页面
        支付本身就是纯签名操作，不需要缓存；微信 Native 码有效期有限，缓存
        旧码反而会让租户扫到过期二维码）。租户重开结账页 / 刷新页面时调用，
        不影响订单状态机（channel 未配置/网关调用失败只是拿不到链接，订单
        照旧是合法的 checkout_pending，等人工确认收款）。
        """
        logger.info(f"重取支付意图 | order={order_id} tenant={tenant_id}")
        order = await OrderRepository(self.session).get_fresh(order_id)
        if order is None or int(order.tenant_id) != tenant_id:
            raise NotFoundException("订单")
        plan_name = await self._plan_name_of(order)
        out = self._to_out(order, plan_name)
        if order.status == "checkout_pending" and order.channel in _ONLINE:
            await self._attach_online_intent(
                out, str(order.channel), int(order.amount_cents), plan_name,
            )
        return out

    async def list_orders(self, tenant_id: int) -> list[OrderOut]:
        logger.info(f"列出订单 | tenant={tenant_id}")
        rows = await OrderRepository(self.session).list_tenant_with_plan_name(tenant_id)
        outs: list[OrderOut] = []
        for order, plan_name in rows:
            name = plan_name or ("中转" if order.product_code == "relay" else "")
            outs.append(self._to_out(order, name))
        return outs

    async def _plan_name_of(self, order: Order) -> str:
        if order.plan_id is None:
            return "中转" if order.product_code == "relay" else ""
        plan = await self.session.get(Plan, order.plan_id)
        return str(plan.name) if plan is not None else ""

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
