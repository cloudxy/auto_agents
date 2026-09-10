"""合集边解析：出处+引用，忽略 listing；黑名单/软删跳过并审计。"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.power_market.types import (
    READABLE_ASSET_TYPES,
    REF_SKIP_ACTION,
    REF_SKIP_BLACKLIST,
    REF_SKIP_DELETED,
    _stored_types_for,
    _to_public_asset_type,
)
from platform_core.exceptions import AuthorizationException, NotFoundException
from platform_core.logger import get_logger
from platform_core.models.capability import CapabilityAsset, CapabilityComponent
from platform_core.models.operation_log import OperationLog

logger = get_logger("service.power_market")


def _assert_observer(user) -> None:
    if user is None:
        return
    if bool(getattr(user, "is_platform_admin", False)):
        return
    raise AuthorizationException(message="需要平台管理员权限")


def _skip_reason(row: CapabilityAsset) -> Optional[str]:
    if row.deleted_at is not None:
        return REF_SKIP_DELETED
    if row.status == "blacklist":
        return REF_SKIP_BLACKLIST
    return None


def _project_ref(row: CapabilityAsset, role: str) -> dict:
    return {
        "name": row.name,
        "asset_type": _to_public_asset_type(row.asset_type),
        "listing_state": row.listing_state,
        "status": row.status,
        "role": role,
    }


async def _load_parent(session: AsyncSession, public_type: Optional[str], name: str):
    types = READABLE_ASSET_TYPES if public_type is None else _stored_types_for(public_type)
    return (await session.execute(
        select(CapabilityAsset).where(
            CapabilityAsset.name == name,
            CapabilityAsset.asset_type.in_(types),
            CapabilityAsset.deleted_at.is_(None),
        )
    )).scalar_one_or_none()


async def _load_edges(session: AsyncSession, parent_id: int):
    stmt = (
        select(CapabilityAsset, CapabilityComponent.role)
        .join(
            CapabilityComponent,
            CapabilityComponent.child_asset_id == CapabilityAsset.id,
        )
        .where(CapabilityComponent.parent_asset_id == parent_id)
        .order_by(CapabilityAsset.id.asc())
    )
    return list((await session.execute(stmt)).all())


def _split_refs(rows) -> tuple[list[dict], list[tuple[str, str]]]:
    items: list[dict] = []
    skipped: list[tuple[str, str]] = []
    for child, role in rows:
        reason = _skip_reason(child)
        if reason:
            skipped.append((str(child.name), reason))
            continue
        items.append(_project_ref(child, str(role)))
    return items, skipped


async def _audit_skips(
    session: AsyncSession, user, parent_name: str, skipped: list[tuple[str, str]],
) -> None:
    if not skipped:
        return
    actor_id = getattr(user, "id", None) if user is not None else None
    actor_name = str(getattr(user, "username", None) or "system")
    for child_name, reason in skipped:
        logger.warning(
            f"power_market.ref.skip | parent={parent_name} "
            f"child={child_name} reason={reason}"
        )
        session.add(OperationLog(
            actor_id=actor_id,
            actor_name=actor_name,
            action=REF_SKIP_ACTION,
            target=f"skill#{child_name}"[:100],
            detail=json.dumps(
                {"parent": parent_name, "child": child_name, "reason": reason},
                ensure_ascii=False,
            ),
        ))
    await session.commit()


async def list_runtime_refs(
    session: AsyncSession, public_type: str, name: str, *, user=None,
) -> dict:
    logger.info(f"power_market.list_runtime_refs | type={public_type} name={name}")
    _assert_observer(user)
    parent = await _load_parent(session, public_type, name)
    if parent is None:
        raise NotFoundException(resource=f"{public_type}/{name}")
    parent_name = str(parent.name)
    parent_type = _to_public_asset_type(parent.asset_type)
    rows = await _load_edges(session, int(parent.id))
    items, skipped = _split_refs(rows)
    await _audit_skips(session, user, parent_name, skipped)
    return {
        "parent": {"name": parent_name, "asset_type": parent_type},
        "items": items,
    }
