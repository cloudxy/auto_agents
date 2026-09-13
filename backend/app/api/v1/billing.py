"""计费 API：公开价目 + 租户订购 + 结账占坑 + 通道通知 + 平台确认收款。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, get_current_user, require_platform_admin
from backend.app.responses import ApiResponse, created, ok
from backend.services.billing_service import BillingService
from backend.services.payment_notify_service import PaymentNotifyService
from backend.services.quota_service import DEFAULT_UPGRADE_PRODUCT
from platform_core.db import get_async_db
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger
from platform_core.schemas.billing import (
    ChannelNotifyIn, CheckoutCreate, OnlinePayChannel, OrderCreate, OrderOut,
    PlanOut, SubscriptionOut,
)

logger = get_logger("api.billing")

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_async_db)) -> BillingService:
    return BillingService(session)


def _notify_svc(session: AsyncSession = Depends(get_async_db)) -> PaymentNotifyService:
    return PaymentNotifyService(session)


@router.get("/plans", response_model=ApiResponse[list[PlanOut]])
async def list_plans(service: BillingService = Depends(_svc)) -> ApiResponse[list[PlanOut]]:
    return ok(await service.list_public_plans())


@router.get("/checkout")
async def preview_checkout(
    product: str = Query(DEFAULT_UPGRADE_PRODUCT),
    user: CurrentUser = Depends(get_current_user),
    service: BillingService = Depends(_svc),
):
    """打开结账：不建单、不验真。静态段先于 /orders/{id}。"""
    logger.info(f"打开结账 | user={user.username} product={product}")
    data = await service.preview_checkout(
        user.tenant_id, user.tenant_role, product,
        is_platform_admin=user.is_platform_admin,
    )
    notice = data.get("notice") or data.get("empty_state") or "操作成功"
    return ok(data=data, message=str(notice))


@router.post("/checkout", response_model=ApiResponse[OrderOut], status_code=201)
async def create_checkout(
    payload: CheckoutCreate,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_db),
    service: BillingService = Depends(_svc),
) -> ApiResponse[OrderOut]:
    """买方创建待支付。不验真、不履约。"""
    logger.info(
        f"提交结账 | user={user.username} product={payload.product} channel={payload.channel}"
    )
    order = await service.create_checkout(
        user.tenant_id, user.tenant_role, payload.product, payload.channel,
        actor_user_id=user.id, is_platform_admin=user.is_platform_admin,
    )
    await record_audit(
        session, user, "checkout.create", f"order#{order.id}",
        detail={"product": payload.product, "channel": payload.channel},
    )
    return created(order, message="待支付已创建")


@router.post("/notify/{channel}")
async def channel_notify(
    channel: OnlinePayChannel,
    payload: ChannelNotifyIn,
    service: PaymentNotifyService = Depends(_notify_svc),
):
    """通道通知入口：无 JWT。验真失败也 200，不开通、无 payment_succeeded。"""
    logger.info(f"通道通知 | channel={channel} order_no={payload.order_no}")
    await service.handle(channel, payload)
    return ok(data={"accepted": True})


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
    """提交线下升级申请（FR-50）。

    角色判定在 Service（业务规则，GWT-50.7/50.8：经办/只读 → 找管理员句，
    不再走 403 FORBIDDEN），Router 只做协议转换。
    """
    if user.tenant_id is None:
        raise BusinessException("需要租户上下文")
    order = await service.create_order(
        user.tenant_id, user.tenant_role, payload, actor_user_id=user.id,
    )
    await record_audit(session, user, "order.create", f"order#{order.id}")
    return created(order, message="升级申请已提交，等待管理员确认收款")


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
    out = await service.confirm_paid(order_id, actor_user_id=user.id)
    await record_audit(session, user, "order.confirm", f"order#{order_id}")
    return ok(out)
