"""能力资产按名查找（审计 B4-4 / P1-20 孪生行修复）

唯一键为 (asset_type, name, alive_flag)：软删行脱离约束，同名可同时存在
「1 条存活 + N 条已软删」。按名查找若不区分生死并用 scalar_one_or_none，
孪生行即 MultipleResultsFound → 500。统一口径：存活行优先，仅剩软删行时取最新一条
（治理视角仍可查看已收回资产）；调用方需要「只看存活」时传 alive_only=True。
"""
from typing import Iterable, Optional, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.logger import get_logger
from platform_core.models.capability import CapabilityAsset

logger = get_logger("service.capability_lookup")


async def find_named_asset(
    session: AsyncSession,
    asset_type: Union[str, Iterable[str]],
    name: str,
    *,
    alive_only: bool = False,
) -> Optional[CapabilityAsset]:
    """按类型 + 名称取一条资产（存活优先；孪生行不再 500）"""
    logger.debug(f"按名查找资产 | type={asset_type} name={name} alive_only={alive_only}")
    types = (asset_type,) if isinstance(asset_type, str) else tuple(asset_type)
    stmt = select(CapabilityAsset).where(
        CapabilityAsset.asset_type.in_(types), CapabilityAsset.name == name,
    )
    if alive_only:
        stmt = stmt.where(CapabilityAsset.deleted_at.is_(None))
    stmt = stmt.order_by(CapabilityAsset.deleted_at.is_(None).desc(), CapabilityAsset.id.desc()).limit(1)
    return (await session.execute(stmt)).scalars().first()
