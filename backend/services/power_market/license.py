"""许可闸写：特例放行仅超管。不拆已订行、不拆引用解析、不合成 listing_state。"""
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.power_market.listing import _load_asset, _public_type
from backend.services.power_market.types import PatchLicenseOverrideRequest, _to_public_asset_type
from platform_core.exceptions import ValidationException
from platform_core.logger import get_logger
from platform_core.models.capability import CapabilityAsset

logger = get_logger("service.power_market")


def _project(row: CapabilityAsset) -> dict:
    return {
        "id": int(row.id),
        "name": row.name,
        "asset_type": _to_public_asset_type(row.asset_type),
        "license": row.license,
        "public_license_override": int(row.public_license_override or 0),
        "listing_state": row.listing_state,
        "status": row.status,
    }


class LicenseWriter:
    """超管写 public_license_override。收回不 DELETE 安装行。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def set_override(
        self, asset_type: str, name: str, payload: PatchLicenseOverrideRequest,
    ) -> dict:
        logger.info(
            f"power_market.set_license_override | type={asset_type} name={name} "
            f"override={payload.public_license_override}"
        )
        flag = int(payload.public_license_override)
        if flag not in (0, 1):
            raise ValidationException(
                "public_license_override 只能是 0 或 1",
                field="public_license_override",
            )
        public = _public_type(asset_type)
        row = await _load_asset(self.session, public, name)
        row.public_license_override = flag
        payload_out = _project(row)
        await self.session.commit()
        return payload_out
