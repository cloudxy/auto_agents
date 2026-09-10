"""上架写：listing_state 与治理/许可/验证分闸。listed_at unlist 不清空。"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.market_events import MARKET_LISTING_CHANGED, emit_market_event
from backend.services.power_market.identity import _is_third_party
from backend.services.power_market.types import (
    LEGACY_ASSET_TYPE_MAP,
    LISTING_BLACKLIST_CODE,
    LISTING_CONFIRM_CODE,
    LISTING_MERGED_CODE,
    LISTING_STATES,
    MERGED_PLUGIN_NAME,
    MSG_LISTING_BLACKLIST,
    MSG_LISTING_CONFIRM,
    MSG_LISTING_MERGED,
    PUBLIC_ASSET_TYPES,
    PatchListingRequest,
    _stored_types_for,
    _to_public_asset_type,
)
from platform_core.exceptions import BusinessException, NotFoundException, ValidationException
from platform_core.logger import get_logger
from platform_core.models.capability import CapabilityAsset

logger = get_logger("service.power_market")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _public_type(raw: str) -> str:
    if raw in PUBLIC_ASSET_TYPES:
        return raw
    mapped = LEGACY_ASSET_TYPE_MAP.get(raw)
    if mapped:
        return mapped
    raise ValidationException("没有这种类型", field="asset_type")


async def _load_asset(session: AsyncSession, public_type: str, name: str) -> CapabilityAsset:
    types = _stored_types_for(public_type)
    row = (await session.execute(
        select(CapabilityAsset).where(
            CapabilityAsset.name == name,
            CapabilityAsset.asset_type.in_(types),
            CapabilityAsset.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if row is None:
        raise NotFoundException(resource=f"{public_type} {name}")
    return row


def _guard_state(listing_state: str) -> None:
    if listing_state not in LISTING_STATES:
        raise ValidationException("上架态只能是 unlisted/listed/coming_soon", field="listing_state")


def _guard_merged(row: CapabilityAsset, listing_state: str) -> None:
    if listing_state != "listed":
        return
    if row.asset_type == "plugin" and row.name == MERGED_PLUGIN_NAME:
        raise BusinessException(
            message=MSG_LISTING_MERGED, code=LISTING_MERGED_CODE, status_code=400,
        )


def _guard_blacklist(row: CapabilityAsset, listing_state: str) -> None:
    if listing_state == "listed" and (row.status or "") == "blacklist":
        raise BusinessException(
            message=MSG_LISTING_BLACKLIST, code=LISTING_BLACKLIST_CODE, status_code=409,
        )


def _guard_third_party(row: CapabilityAsset, listing_state: str, confirm: bool) -> None:
    if listing_state != "listed" or confirm or not _is_third_party(row):
        return
    raise BusinessException(
        message=MSG_LISTING_CONFIRM.format(name=row.name),
        code=LISTING_CONFIRM_CODE,
        status_code=409,
    )


def _apply_listed_at(row: CapabilityAsset, listing_state: str) -> None:
    if listing_state == "listed" and (row.listing_state or "") != "listed":
        row.listed_at = _utcnow()


def _project(row: CapabilityAsset) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "asset_type": _to_public_asset_type(row.asset_type),
        "listing_state": row.listing_state,
        "listed_at": row.listed_at.isoformat() if row.listed_at else None,
        "status": row.status,
        "source_type": row.source_type,
    }


class ListingWriter:
    """超管上架写。不改治理 status，不看 health。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def set_listing(
        self, asset_type: str, name: str, payload: PatchListingRequest,
    ) -> dict:
        logger.info(
            f"power_market.set_listing | type={asset_type} name={name} "
            f"state={payload.listing_state}"
        )
        public = _public_type(asset_type)
        _guard_state(payload.listing_state)
        row = await _load_asset(self.session, public, name)
        _guard_merged(row, payload.listing_state)
        _guard_blacklist(row, payload.listing_state)
        _guard_third_party(row, payload.listing_state, bool(payload.confirm))
        old_state = row.listing_state
        _apply_listed_at(row, payload.listing_state)
        row.listing_state = payload.listing_state
        payload_out = _project(row)
        await self.session.commit()
        await emit_market_event(
            self.session, MARKET_LISTING_CHANGED,
            props={"old_state": old_state, "new_state": payload.listing_state},
        )
        return payload_out
