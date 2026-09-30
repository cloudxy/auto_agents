"""租户运行时设置（交付 webhook 等）。

交付 webhook（审计 BUG-22 / P0-8）：
- 设置时经 platform_core.outbound_guard 校验：只允许解析到公网的 http(s) 地址；
- 签名密钥按租户独立生成（首次设置 URL 时生成，可轮换）——平台共享密钥既不能
  交给租户验签，也会让各租户签名同源；租户管理员可在设置页读取本企业密钥验签。
"""
import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.exceptions import NotFoundException, ValidationException
from platform_core.logger import get_logger
from platform_core.models.tenant import Tenant
from platform_core.outbound_guard import OutboundBlocked, assert_public_url

logger = get_logger("service.tenant_settings")

_URL_KEY = "delivery_webhook_url"
_SECRET_KEY = "delivery_webhook_secret"


def _new_secret() -> str:
    return f"whsec_{secrets.token_hex(24)}"


class TenantSettingsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _tenant(self, tenant_id: int) -> Tenant:
        tenant = await self.session.get(Tenant, tenant_id)
        if tenant is None:
            raise NotFoundException("租户")
        return tenant

    async def set_delivery_webhook(self, tenant_id: int, url: str | None,
                                   *, rotate_secret: bool = False) -> dict:
        logger.info(f"设置交付 webhook | tenant={tenant_id} rotate={rotate_secret}")
        tenant = await self._tenant(tenant_id)
        cleaned = (url or "").strip()
        if cleaned and not (cleaned.startswith("https://") or cleaned.startswith("http://")):
            raise ValidationException(message="webhook 须为 http(s) URL", field="url")
        if cleaned:
            try:
                await assert_public_url(cleaned)
            except OutboundBlocked as exc:
                logger.warning(f"交付 webhook 地址被拒 | tenant={tenant_id}")
                raise ValidationException(message=f"webhook 地址不可用：{exc.message}", field="url") from exc
        quota = dict(tenant.quota or {})
        if cleaned:
            quota[_URL_KEY] = cleaned
            if rotate_secret or not quota.get(_SECRET_KEY):
                quota[_SECRET_KEY] = _new_secret()
        else:
            quota.pop(_URL_KEY, None)
        tenant.quota = quota
        await self.session.commit()
        return self._view(quota)

    async def get_delivery_webhook(self, tenant_id: int) -> str | None:
        logger.info(f"读取交付 webhook | tenant={tenant_id}")
        url, _secret = await self.get_delivery_config(tenant_id)
        return url

    async def get_delivery_config(self, tenant_id: int) -> tuple[str | None, str | None]:
        """(url, 签名密钥)；未配置返回 (None, None)"""
        tenant = await self._tenant(tenant_id)
        quota = tenant.quota if isinstance(tenant.quota, dict) else {}
        url = quota.get(_URL_KEY)
        secret = quota.get(_SECRET_KEY)
        return (str(url) if url else None), (str(secret) if secret else None)

    async def get_delivery_view(self, tenant_id: int) -> dict:
        tenant = await self._tenant(tenant_id)
        return self._view(tenant.quota if isinstance(tenant.quota, dict) else {})

    @staticmethod
    def _view(quota: dict) -> dict:
        url = quota.get(_URL_KEY)
        return {
            "delivery_webhook_url": str(url) if url else None,
            "signing_secret": (str(quota.get(_SECRET_KEY)) if url and quota.get(_SECRET_KEY) else None),
        }
