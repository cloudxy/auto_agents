"""计费 API：公开价目 + 租户订购 + 结账占坑 + 通道通知 + 平台确认收款。"""
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import (
    CurrentUser, get_current_user, require_platform_admin_or_404,
)
from backend.app.responses import ApiResponse, created, ok
from backend.services.billing_service import BillingService
from backend.services.payment_notify_service import PaymentNotifyService
from backend.services.quota_service import (
    CHECKOUT_UNCONFIGURED_SUBMIT_USER,
    DEFAULT_UPGRADE_PRODUCT,
)
from platform_core.db import get_async_db
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger
from platform_core.schemas.billing import (
    ChannelNotifyIn, CheckoutCreate, OnlinePayChannel, OrderConfirmIn, OrderCreate,
    OrderOut, PlanGrantIn, PlanOut, SubscriptionOut,
)

logger = get_logger("api.billing")

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_async_db)) -> BillingService:
    return BillingService(session)


def _notify_svc(session: AsyncSession = Depends(get_async_db)) -> PaymentNotifyService:
    return PaymentNotifyService(session)


def _fixture_notify_enabled() -> bool:
    from config import settings

    if os.getenv("APP_ENV", "local") == "prod":
        return False
    section = settings.get("BILLING") or {}  # 先取段再取键（点路径会在 Dynaconf 内部带 parent 递归）
    value = section.get("FIXTURE_NOTIFY_ENABLED") if hasattr(section, "get") else None
    return True if value is None else bool(value)


@router.get("/plans", response_model=ApiResponse[list[PlanOut]])
async def list_plans(service: BillingService = Depends(_svc)) -> ApiResponse[list[PlanOut]]:
    return ok(await service.list_public_plans())


@router.get("/checkout")
async def preview_checkout(
    product: str = Query(DEFAULT_UPGRADE_PRODUCT),
    referrer_surface: Optional[str] = Query(None),
    user: CurrentUser = Depends(get_current_user),
    service: BillingService = Depends(_svc),
):
    """打开结账：不建单、不验真。静态段先于 /orders/{id}。"""
    logger.info(f"打开结账 | user={user.username} product={product}")
    data = await service.preview_checkout(
        user.tenant_id, user.tenant_role, product,
        is_platform_admin=user.is_platform_admin,
        actor_user_id=user.id,
        referrer_surface=referrer_surface or "nav",
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
    await record_audit(user, "checkout.create", f"order#{order.id}",
        detail={"product": payload.product, "channel": payload.channel},
    )
    message = (
        CHECKOUT_UNCONFIGURED_SUBMIT_USER if not order.channel else "待支付已创建"
    )
    return created(order, message=message)


@router.post("/notify/{channel}")
async def channel_notify(
    channel: OnlinePayChannel,
    payload: ChannelNotifyIn,
    service: PaymentNotifyService = Depends(_notify_svc),
):
    """HMAC 夹具通知入口（沙箱 / CI）：无 JWT。验真失败也 200，不开通、无 payment_succeeded。

    审计 R1-11：夹具通路与真实网关共用同一份商户密钥，prod 恒关闭（404 同形），
    其它环境可用 BILLING.FIXTURE_NOTIFY_ENABLED=false 关闭；真实回调走 /external/v1/payments/*。
    """
    if not _fixture_notify_enabled():
        raise HTTPException(status_code=404, detail="Not Found")
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
    await record_audit(user, "order.create", f"order#{order.id}")
    return created(order, message="升级申请已提交，等待管理员确认收款")


@router.get("/orders/{order_id}/pay-intent", response_model=ApiResponse[OrderOut])
async def regenerate_pay_intent(
    order_id: int,
    user: CurrentUser = Depends(get_current_user),
    service: BillingService = Depends(_svc),
) -> ApiResponse[OrderOut]:
    """按需重取在线支付链接/二维码（未持久化，见 BillingService.regenerate_pay_intent）。
    只在自己企业的订单上生效——跨企业订单号走 tenant_id 核对，不是路径参数就能查。
    """
    if user.tenant_id is None:
        raise BusinessException("需要租户上下文")
    order = await service.regenerate_pay_intent(order_id, user.tenant_id)
    return ok(data=order)


@router.post("/orders/{order_id}/cancel", response_model=ApiResponse[OrderOut])
async def cancel_order(
    order_id: int,
    user: CurrentUser = Depends(get_current_user),
    service: BillingService = Depends(_svc),
) -> ApiResponse[OrderOut]:
    """买方取消本企业待支付单（审计 BUG-24）；已付款 / 已关闭 409，跨企业 404"""
    out = await service.cancel_checkout(
        order_id, user.tenant_id, user.tenant_role, actor_user_id=user.id,
    )
    await record_audit(user, "order.cancel", f"order#{order_id}")
    return ok(out, message="订单已取消")


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
    _user: CurrentUser = Depends(require_platform_admin_or_404),
    service: BillingService = Depends(_svc),
) -> ApiResponse[list[OrderOut]]:
    return ok(await service.list_pending_orders())


@router.post("/admin/tenants/{tenant_id}/grant", response_model=ApiResponse[OrderOut])
async def grant_plan(
    tenant_id: int,
    payload: PlanGrantIn,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    service: BillingService = Depends(_svc),
) -> ApiResponse[OrderOut]:
    """平台为定制客户开通套餐（决策 D17）：记一笔线下已收款订单并按同一履约路径开通"""
    out = await service.grant_plan(
        tenant_id, payload.product, payload.amount_cents, payload.periods,
        note=payload.note, actor_user_id=user.id,
    )
    await record_audit(user, "plan.grant", f"tenant#{tenant_id}",
                       detail={"product": payload.product, "periods": payload.periods,
                               "amount_cents": payload.amount_cents, "note": payload.note})
    return ok(out, message="已开通")


@router.post("/orders/{order_id}/retry-fulfillment", response_model=ApiResponse[OrderOut])
async def retry_order_fulfillment(
    order_id: int,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    service: BillingService = Depends(_svc),
) -> ApiResponse[OrderOut]:
    """超管补偿：已付款待开通的单重新履约（审计 BUG-25）"""
    out = await service.retry_fulfillment(order_id)
    await record_audit(user, "order.retry_fulfillment", f"order#{order_id}")
    return ok(out, message="已重新开通")


@router.post("/orders/{order_id}/confirm", response_model=ApiResponse[OrderOut])
async def confirm_order(
    order_id: int,
    payload: OrderConfirmIn | None = None,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
    service: BillingService = Depends(_svc),
) -> ApiResponse[OrderOut]:
    expected = payload.order_id if payload is not None else None
    out = await service.confirm_paid(
        order_id, actor_user_id=user.id, expected_order_id=expected,
    )
    await record_audit(user, "order.confirm", f"order#{order_id}")
    return ok(out)
