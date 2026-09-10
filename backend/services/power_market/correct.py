"""D5：纠正对第三方不可用，不写源树。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.power_market.identity import _is_third_party
from backend.services.power_market.types import (
    CORRECT_THIRD_PARTY_CODE,
    MSG_CORRECT_THIRD_PARTY,
)
from platform_core.exceptions import BusinessException, NotFoundException, ValidationException
from platform_core.logger import get_logger
from platform_core.models.capability import CapabilityAsset

logger = get_logger("service.power_market")


class CorrectGuard:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def correct(self, asset_type: str, name: str, payload: dict) -> dict:
        logger.info(f"power_market.correct | type={asset_type} name={name}")
        row = (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == asset_type,
                CapabilityAsset.name == name,
                CapabilityAsset.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundException(resource=f"{asset_type} {name}")
        if _is_third_party(row):
            raise BusinessException(
                message=MSG_CORRECT_THIRD_PARTY,
                code=CORRECT_THIRD_PARTY_CODE,
                status_code=409,
            )
        if not payload:
            raise ValidationException("无可矫正字段", field="payload")
        return {
            "name": row.name,
            "written_back": False,
            "db_only": True,
            "message": "第一方纠正走技能治理写回，本接口不写第三方源树",
        }
