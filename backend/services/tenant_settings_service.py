"""租户运行时设置（交付 webhook 等）。"""
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.exceptions import NotFoundException, ValidationException
from platform_core.logger import get_logger
from platform_core.models.tenant import Tenant

logger = get_logger("service.tenant_settings")


class TenantSettingsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def set_delivery_webhook(self, tenant_id: int, url: str | None) -> dict:
        logger.info(f"设置交付 webhook | tenant={tenant_id}")
        tenant = await self.session.get(Tenant, tenant_id)
        if tenant is None:
            raise NotFoundException("租户")
        cleaned = (url or "").strip()
        if cleaned and not (cleaned.startswith("https://") or cleaned.startswith("http://")):
            raise ValidationException(message="webhook 须为 http(s) URL", field="url")
        quota = dict(tenant.quota or {})
        if cleaned:
            quota["delivery_webhook_url"] = cleaned
        else:
            quota.pop("delivery_webhook_url", None)
        tenant.quota = quota
        await self.session.commit()
        return {"delivery_webhook_url": cleaned or None}

    async def get_delivery_webhook(self, tenant_id: int) -> str | None:
        logger.info(f"读取交付 webhook | tenant={tenant_id}")
        tenant = await self.session.get(Tenant, tenant_id)
        if tenant is None:
            raise NotFoundException("租户")
        quota = tenant.quota or {}
        url = quota.get("delivery_webhook_url") if isinstance(quota, dict) else None
        return str(url) if url else None
