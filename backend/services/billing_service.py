"""订阅计费：价目、下单、人工确认收款、套用配额。在线支付未开通。"""
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.payment_provider import get_payment_provider
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.models.billing import Order, Plan, TenantSubscription
from platform_core.models.tenant import Tenant
from platform_core.schemas.billing import OrderCreate, OrderOut, PlanOut, SubscriptionOut

logger = get_logger("service.billing")

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

    async def create_order(self, tenant_id: int, payload: OrderCreate) -> OrderOut:
        logger.info(f"创建订单 | tenant={tenant_id} plan={payload.plan_id} channel={payload.channel}")
        if payload.channel in ("alipay", "wechat"):
            get_payment_provider(payload.channel).collect(
                order_id=0, amount_cents=0, channel=payload.channel,
            )
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
            channel=payload.channel or "offline",
        )
        self.session.add(order)
        await self.session.flush()
        get_payment_provider(order.channel).collect(
            order_id=int(order.id), amount_cents=int(order.amount_cents), channel=order.channel,
        )
        await self.session.commit()
        await self.session.refresh(order)
        return OrderOut.model_validate(order)

    async def list_orders(self, tenant_id: int) -> list[OrderOut]:
        logger.info(f"列出订单 | tenant={tenant_id}")
        rows = (await self.session.execute(
            select(Order).where(Order.tenant_id == tenant_id).order_by(Order.id.desc())
        )).scalars().all()
        return [OrderOut.model_validate(r) for r in rows]

    async def list_pending_orders(self) -> list[OrderOut]:
        logger.info("列出待确认收款订单")
        rows = (await self.session.execute(
            select(Order).where(Order.status == "pending").order_by(Order.id.desc())
        )).scalars().all()
        return [OrderOut.model_validate(r) for r in rows]

    async def confirm_paid(self, order_id: int) -> OrderOut:
        logger.info(f"确认收款 | order={order_id}")
        order = await self.session.get(Order, order_id)
        if order is None:
            raise NotFoundException("订单")
        if order.status == "paid":
            return OrderOut.model_validate(order)
        plan = await self.session.get(Plan, order.plan_id)
        if plan is None:
            raise BusinessException("套餐已下架")
        now = datetime.now(timezone.utc)
        order.status = "paid"
        order.paid_at = now
        await self._apply_plan(order.tenant_id, plan, now)
        await self.session.commit()
        await self.session.refresh(order)
        return OrderOut.model_validate(order)

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
