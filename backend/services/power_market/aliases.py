"""人工短名写：撞存活目录短名或存活 alias → 409，两边不变。同步不建。"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.power_market.listing import _load_asset, _public_type
from backend.services.power_market.types import (
    ALIAS_CONFLICT_CODE,
    MSG_ALIAS_CONFLICT,
    PutAliasRequest,
    _to_public_asset_type,
)
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger
from platform_core.models.capability import CapabilityAlias, CapabilityAsset

logger = get_logger("service.power_market")


def _project(row: CapabilityAlias) -> dict:
    return {
        "id": int(row.id),
        "slug": row.slug,
        "asset_id": int(row.asset_id),
        "asset_type": _to_public_asset_type(row.asset_type),
    }


def _conflict() -> None:
    raise BusinessException(
        message=MSG_ALIAS_CONFLICT, code=ALIAS_CONFLICT_CODE, status_code=409,
    )


async def _live_for_asset(session: AsyncSession, asset_id: int) -> CapabilityAlias | None:
    return (await session.execute(
        select(CapabilityAlias).where(
            CapabilityAlias.asset_id == asset_id,
            CapabilityAlias.deleted_at.is_(None),
        )
    )).scalar_one_or_none()


async def _slug_taken(
    session: AsyncSession, slug: str, *, skip_alias_id: int | None = None,
) -> bool:
    catalog = (await session.execute(
        select(CapabilityAsset.id).where(
            CapabilityAsset.name == slug,
            CapabilityAsset.deleted_at.is_(None),
        ).limit(1)
    )).first()
    if catalog is not None:
        return True
    stmt = select(CapabilityAlias.id).where(
        CapabilityAlias.slug == slug,
        CapabilityAlias.deleted_at.is_(None),
    )
    if skip_alias_id is not None:
        stmt = stmt.where(CapabilityAlias.id != skip_alias_id)
    return (await session.execute(stmt.limit(1))).first() is not None


class AliasWriter:
    """超管指定/改 alias。一资产一条存活行。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def set_alias(
        self, asset_type: str, name: str, payload: PutAliasRequest, *, actor: str,
    ) -> dict:
        logger.info(
            f"power_market.set_alias | type={asset_type} name={name} slug={payload.slug}"
        )
        public = _public_type(asset_type)
        row = await _load_asset(self.session, public, name)
        existing = await _live_for_asset(self.session, int(row.id))
        if existing is not None and existing.slug == payload.slug:
            return _project(existing)
        skip = int(existing.id) if existing is not None else None
        if await _slug_taken(self.session, payload.slug, skip_alias_id=skip):
            _conflict()
        return await self._persist(row, existing, payload.slug, actor)

    async def _persist(
        self, asset: CapabilityAsset, existing: CapabilityAlias | None,
        slug: str, actor: str,
    ) -> dict:
        if existing is not None:
            existing.slug = slug
            existing.asset_type = asset.asset_type
            existing.updated_by = actor
            target = existing
        else:
            target = CapabilityAlias(
                slug=slug, asset_id=int(asset.id), asset_type=asset.asset_type,
                tenant_id=None, created_by=actor, updated_by=actor,
            )
            self.session.add(target)
        try:
            await self.session.flush()
            out = _project(target)
            await self.session.commit()
            return out
        except IntegrityError:
            await self.session.rollback()
            _conflict()
            raise
