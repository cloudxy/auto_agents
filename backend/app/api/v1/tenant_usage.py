"""租户用量看板 API（SaaS S3-2）——当前租户三指标 vs 配额 + LLM 分摊

读：任意已登录租户成员（含只读 viewer）可见进度。
写套餐：owner/admin；本波不提供自助改套餐（支付仍 FR-50）。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import CurrentUser, require_login
from backend.app.api.v1.members import require_tenant_manager
from backend.app.responses import ok
from backend.services.quota_service import (
    DEFAULT_UPGRADE_PRODUCT,
    SHANGHAI_TZ,
    QuotaService,
    resolve_upgrade_intent,
    shanghai_year_month,
)
from backend.services.tenant_settings_service import TenantSettingsService
from platform_core.db import get_async_db
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger
from pydantic import BaseModel, Field

logger = get_logger("api.tenant_usage")

router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> QuotaService:
    return QuotaService(session)


def _require_tenant_space(user: CurrentUser) -> int:
    if not user.tenant_id:
        raise BusinessException(message="用量属于企业空间", code="USAGE_NEEDS_TENANT")
    return int(user.tenant_id)


@router.get("/usage")
async def tenant_usage_overview(
    user: CurrentUser = Depends(require_login),
    service: QuotaService = Depends(_service),
):
    """本租户用量看板（Asia/Shanghai 月；只读成员可看进度，不能改套餐）"""
    if not user.tenant_id:
        logger.info(f"用量读·无企业空间 | user={user.username}")
        return ok(data={
            "scope": "platform",
            "message": "用量属于企业空间",
            "timezone": SHANGHAI_TZ,
        })
    year_month = shanghai_year_month()
    logger.debug(f"用量看板 | tenant={user.tenant_id} month={year_month}")
    return ok(data=await service.usage_overview(user.tenant_id, year_month))


@router.get("/usage/by-member")
async def tenant_usage_by_member(
    user: CurrentUser = Depends(require_login),
    service: QuotaService = Depends(_service),
):
    """成员维度用量分摊（任务创建数按成员聚合；只读可见）"""
    tid = _require_tenant_space(user)
    return ok(data=await service.usage_by_member(tid))


class DeliveryWebhookIn(BaseModel):
    url: str | None = Field(default=None, max_length=500)


@router.get("/delivery-webhook")
async def get_delivery_webhook(
    user: CurrentUser = Depends(require_tenant_manager),
    session: AsyncSession = Depends(get_async_db),
):
    if user.tenant_id is None:
        raise BusinessException("需要租户上下文")
    url = await TenantSettingsService(session).get_delivery_webhook(user.tenant_id)
    return ok(data={"delivery_webhook_url": url})


@router.put("/delivery-webhook")
async def put_delivery_webhook(
    payload: DeliveryWebhookIn,
    user: CurrentUser = Depends(require_tenant_manager),
    session: AsyncSession = Depends(get_async_db),
):
    if user.tenant_id is None:
        raise BusinessException("需要租户上下文")
    data = await TenantSettingsService(session).set_delivery_webhook(user.tenant_id, payload.url)
    return ok(data=data)


@router.get("/quota/upgrade-intent")
async def quota_upgrade_intent(
    product: str = Query(DEFAULT_UPGRADE_PRODUCT),
    user: CurrentUser = Depends(require_login),
):
    """申请提升分角色着陆（GWT-U02.6/U02.7）：不创建待支付。"""
    _require_tenant_space(user)
    logger.info(
        f"申请提升意图 | user={user.username} role={user.tenant_role} product={product}"
    )
    return ok(data=resolve_upgrade_intent(user.tenant_role, product))


@router.patch("/quota")
async def patch_tenant_quota(
    user: CurrentUser = Depends(require_tenant_manager),
):
    """改套餐写权：只读 403。本波不可自助改套餐（申请提升走联系说明）。"""
    logger.info(f"改套餐拒绝（本波锁定） | user={user.username} tenant={user.tenant_id}")
    raise BusinessException(
        message="本波不可自助改套餐。请申请提升。",
        code="QUOTA_PLAN_LOCKED",
    )
