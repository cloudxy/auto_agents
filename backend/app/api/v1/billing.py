"""计费 API：公开价目 + 租户订购 + 平台确认收款。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, get_current_user, require_platform_admin
from backend.app.responses import ApiResponse, created, ok
from backend.services.billing_service import BillingService
from platform_core.db import get_async_db
from platform_core.exceptions import BusinessException
from platform_core.schemas.billing import OrderCreate, OrderOut, PlanOut, SubscriptionOut

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_async_db)) -> BillingService:
    return BillingService(session)


@router.get("/plans", response_model=ApiResponse[list[PlanOut]])
async def list_plans(service: BillingService = Depends(_svc)) -> ApiResponse[list[PlanOut]]:
    return ok(await service.list_public_plans())


@router.get("/subscription", response_model=ApiResponse[SubscriptionOut | None])
async def get_subscription(
    user: CurrentUser = Depends(get_current_user),
    service: BillingService = Depends(_svc),
) -> ApiResponse[SubscriptionOut | None]:
    if user.tenant_id is None:
        raise BusinessException("需要租户上下文")
    return ok(await service.get_subscription(user.tenant_id))


@router.post("/orders", response_model=ApiResponse[OrderOut], status_code=201)
async def create_order(
    payload: OrderCreate,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_db),
    service: BillingService = Depends(_svc),
) -> ApiResponse[OrderOut]:
    if user.tenant_id is None:
        raise BusinessException("需要租户上下文")
    order = await service.create_order(user.tenant_id, payload)
    await record_audit(session, user, "order.create", f"order#{order.id}")
    return created(order)


@router.get("/orders", response_model=ApiResponse[list[OrderOut]])
async def list_orders(
    user: CurrentUser = Depends(get_current_user),
    service: BillingService = Depends(_svc),
) -> ApiResponse[list[OrderOut]]:
    if user.tenant_id is None:
        raise BusinessException("需要租户上下文")
    return ok(await service.list_orders(user.tenant_id))


@router.get("/admin/orders", response_model=ApiResponse[list[OrderOut]])
async def list_pending_orders(
    _user: CurrentUser = Depends(require_platform_admin),
    service: BillingService = Depends(_svc),
) -> ApiResponse[list[OrderOut]]:
    return ok(await service.list_pending_orders())


@router.post("/orders/{order_id}/confirm", response_model=ApiResponse[OrderOut])
async def confirm_order(
    order_id: int,
    user: CurrentUser = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_async_db),
    service: BillingService = Depends(_svc),
) -> ApiResponse[OrderOut]:
    out = await service.confirm_paid(order_id)
    await record_audit(session, user, "order.confirm", f"order#{order_id}")
    return ok(out)
