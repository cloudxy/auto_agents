"""订单仓储：结账占坑查询 + 通知 CAS。一企一商品非终态靠 UNIQUE 兜底。"""
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from platform_core.models.billing import Order, Plan
from platform_core.repository import BaseRepository

_OPEN = ("checkout_pending", "paid_pending_fulfillment", "pending")
_VERIFY_FROM = ("checkout_pending",)
_FULFILL_FROM = ("paid_pending_fulfillment",)
_FAIL_FROM = ("checkout_pending",)
_LATE_FROM = ("unpaid", "fulfilled")
_CONFIRM_FROM = ("checkout_pending",)


class OrderRepository(BaseRepository[Order]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Order, session=session)

    async def get_open_for_product(
        self, tenant_id: int, product_code: str,
    ) -> Optional[Order]:
        stmt = select(Order).where(
            Order.tenant_id == tenant_id,
            Order.product_code == product_code,
            Order.status.in_(_OPEN),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_order_no(self, order_no: str) -> Optional[Order]:
        if not order_no:
            return None
        stmt = select(Order).where(Order.order_no == order_no)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_fresh(self, order_id: int) -> Optional[Order]:
        stmt = (
            select(Order)
            .where(Order.id == order_id)
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_latest_for_product(
        self, tenant_id: int, product_code: str,
    ) -> Optional[Order]:
        stmt = (
            select(Order)
            .where(Order.tenant_id == tenant_id, Order.product_code == product_code)
            .order_by(Order.id.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def cas_status(
        self, order_id: int, from_statuses: tuple[str, ...], values: dict,
        *, amount_cents: int | None = None,
    ) -> int:
        cond = [Order.id == order_id, Order.status.in_(from_statuses)]
        if amount_cents is not None:
            cond.append(Order.amount_cents == amount_cents)
        stmt = (
            update(Order)
            .where(*cond)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)

    async def cas_confirm_checkout(
        self, order_id: int, amount_cents: int, now: datetime,
    ) -> int:
        return await self.cas_status(order_id, _CONFIRM_FROM, {
            "status": "fulfilled", "fulfilled_at": now, "paid_at": now,
        }, amount_cents=amount_cents)

    async def cas_mark_verified(
        self, order_id: int, now: datetime, channel_trade_no: Optional[str],
    ) -> int:
        values: dict = {
            "status": "paid_pending_fulfillment",
            "verified_at": now,
            "paid_at": now,
        }
        if channel_trade_no:
            values["channel_trade_no"] = channel_trade_no
        return await self.cas_status(order_id, _VERIFY_FROM, values)

    async def cas_mark_fulfilled(self, order_id: int, now: datetime) -> int:
        return await self.cas_status(order_id, _FULFILL_FROM, {
            "status": "fulfilled", "fulfilled_at": now,
        })

    async def cas_mark_unpaid(
        self, order_id: int, now: datetime, reason: str,
    ) -> int:
        return await self.cas_status(order_id, _FAIL_FROM, {
            "status": "unpaid", "fail_reason": reason, "unpaid_at": now,
        })

    async def mark_late_notify(self, order_id: int, now: datetime) -> int:
        return await self.cas_status(order_id, _LATE_FROM, {"late_notify_at": now})

    async def list_tenant_with_plan_name(
        self, tenant_id: int,
    ) -> list[tuple[Order, Optional[str]]]:
        plan = aliased(Plan)
        stmt = (
            select(Order, plan.name)
            .outerjoin(plan, Order.plan_id == plan.id)
            .where(Order.tenant_id == tenant_id)
            .order_by(Order.id.desc())
        )
        return list((await self.session.execute(stmt)).all())
