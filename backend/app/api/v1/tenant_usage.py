"""租户用量看板 API（SaaS S3-2）——当前租户三指标 vs 配额 + LLM 分摊"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import CurrentUser
from backend.app.api.v1.members import require_tenant_manager
from backend.app.responses import ok
from platform_core.exceptions import BusinessException
from backend.services.quota_service import QuotaService
from backend.services.tenant_settings_service import TenantSettingsService
from platform_core.db import get_async_db
from pydantic import BaseModel, Field

router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> QuotaService:
    return QuotaService(session)


@router.get("/usage")
async def tenant_usage_overview(
    user: CurrentUser = Depends(require_tenant_manager),
    service: QuotaService = Depends(_service),
):
    """本租户用量看板（当月；三指标 vs 配额 + LLM 按供应商分摊）"""
    year_month = datetime.utcnow().strftime("%Y-%m")
    return ok(data=await service.usage_overview(user.tenant_id, year_month))


@router.get("/usage/by-member")
async def tenant_usage_by_member(
    user: CurrentUser = Depends(require_tenant_manager),
    service: QuotaService = Depends(_service),
):
    """成员维度用量分摊（B6：任务创建数按成员聚合，租户管理者视角）"""
    return ok(data=await service.usage_by_member(user.tenant_id))


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
