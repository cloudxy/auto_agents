"""安装行写/读：订这一行，不礼包，不占三类配额。卸一行不连坐。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.market_events import MARKET_UNINSTALLED, emit_market_event
from backend.services.power_market.types import (
    HOST_LABELS,
    LISTING_VISIBLE,
    MARKET_HOST_INCOMPAT_CODE,
    MARKET_NEEDS_TENANT_CODE,
    MARKET_READONLY_ROLE_CODE,
    MSG_ALREADY_SUBSCRIBED,
    MSG_DELISTED,
    MSG_DELISTED_RESUBSCRIBE,
    MSG_FLAGS_LOCKED,
    MSG_INSTALL_READONLY,
    MSG_NEEDS_TENANT,
    MSG_READONLY_ROLE,
    MSG_SUBSCRIBED,
    PUBLIC_HOSTS,
    _to_public_asset_type,
)
from platform_core.exceptions import BusinessException, NotFoundException, ValidationException
from platform_core.logger import get_logger
from platform_core.models.capability import CapabilityAsset, CapabilityInstall

logger = get_logger("service.power_market")

_READONLY_ROLES = frozenset({"viewer"})
_WRITABLE_TENANT_ROLES = frozenset({"owner", "admin", "operator"})


def hosts_for_asset(row: CapabilityAsset) -> list[str]:
    logger.debug("power_market.hosts_for_asset")
    declared = _declared_hosts(row)
    if declared is None:
        return list(PUBLIC_HOSTS)
    return [h for h in PUBLIC_HOSTS if h in declared]


def _declared_hosts(row: CapabilityAsset) -> Optional[list[str]]:
    raw = getattr(row, "host_compat", None)
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        return None
    return [str(item) for item in raw]


def _host_label(host: str) -> str:
    return HOST_LABELS.get(host, host)


def _is_readonly(user) -> bool:
    tenant_role = str(getattr(user, "tenant_role", None) or "").strip()
    if tenant_role:
        return tenant_role not in _WRITABLE_TENANT_ROLES
    role = str(getattr(user, "role", None) or "").strip()
    return role in _READONLY_ROLES


def _require_tenant(user) -> int:
    if user is None or getattr(user, "tenant_id", None) is None:
        raise BusinessException(
            message=MSG_NEEDS_TENANT, code=MARKET_NEEDS_TENANT_CODE, status_code=403,
        )
    return int(user.tenant_id)


def _assert_writer(user, *, message: str) -> int:
    tenant_id = _require_tenant(user)
    if _is_readonly(user):
        raise BusinessException(
            message=message, code=MARKET_READONLY_ROLE_CODE, status_code=403,
        )
    return tenant_id


def _assert_actor(user) -> int:
    return _assert_writer(user, message=MSG_READONLY_ROLE)


def _assert_host(row: CapabilityAsset, host: Optional[str]) -> str:
    key = (host or "").strip().lower()
    if not key:
        raise ValidationException("请选择宿主", field="host")
    if key not in PUBLIC_HOSTS:
        raise ValidationException("没有这种宿主", field="host")
    allowed = hosts_for_asset(row)
    if key not in allowed:
        declared = _declared_hosts(row)
        if declared == []:
            msg = "该能力未声明支持任何宿主"
        else:
            msg = f"该能力未声明支持 {_host_label(key)}"
        raise BusinessException(
            message=msg, code=MARKET_HOST_INCOMPAT_CODE, status_code=409,
        )
    return key


async def insert_install(
    session: AsyncSession, row: CapabilityAsset, host: str, user,
) -> dict:
    logger.info(f"power_market.insert_install | asset={row.id} host={host}")
    tenant_id = int(user.tenant_id)
    asset_id = int(row.id)
    actor = getattr(user, "username", None)
    session.add(CapabilityInstall(
        tenant_id=tenant_id, asset_id=asset_id, host=host,
        created_by=actor, updated_by=actor,
    ))
    try:
        await session.flush()
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return await _already(session, tenant_id, asset_id, host)
    return {
        "created": True,
        "already_subscribed": False,
        "message": MSG_SUBSCRIBED.format(host=_host_label(host)),
        "host": host,
        "asset_id": asset_id,
    }


async def _already(session: AsyncSession, tenant_id: int, asset_id: int, host: str) -> dict:
    logger.info(f"power_market.subscribe_idempotent | asset={asset_id} host={host}")
    existing = (await session.execute(
        select(CapabilityInstall).where(
            CapabilityInstall.tenant_id == tenant_id,
            CapabilityInstall.asset_id == asset_id,
            CapabilityInstall.host == host,
            CapabilityInstall.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if existing is None:
        raise BusinessException(message="订阅冲突，请重试", code="BUSINESS_ERROR")
    return {
        "created": False,
        "already_subscribed": True,
        "message": MSG_ALREADY_SUBSCRIBED.format(host=_host_label(host)),
        "host": host,
        "asset_id": asset_id,
    }


async def list_tenant_installs(session: AsyncSession, tenant_id: int, user=None) -> dict:
    logger.info(f"power_market.list_tenant_installs | tenant={tenant_id}")
    stmt = (
        select(CapabilityInstall, CapabilityAsset)
        .join(CapabilityAsset, CapabilityAsset.id == CapabilityInstall.asset_id)
        .where(
            CapabilityInstall.tenant_id == tenant_id,
            CapabilityInstall.deleted_at.is_(None),
        )
        .order_by(CapabilityInstall.id.desc())
    )
    pairs = (await session.execute(stmt)).all()
    writer = bool(user) and not _is_readonly(user)
    items = [_project_install(install, asset, writer=writer) for install, asset in pairs]
    return {"total": len(items), "items": items}


async def patch_live_install(
    session: AsyncSession, install_id: int, user, *, enabled=None, trusted=None,
) -> dict:
    logger.info(f"power_market.patch_live_install | id={install_id}")
    tenant_id = _assert_writer(user, message=MSG_INSTALL_READONLY)
    install, asset = await _load_live_pair(session, tenant_id, install_id)
    if _flags_locked(asset):
        raise BusinessException(message=MSG_FLAGS_LOCKED, code="BUSINESS_ERROR", status_code=409)
    if enabled is not None:
        install.enabled = int(enabled)
    if trusted is not None:
        install.trusted = int(trusted)
    install.updated_by = getattr(user, "username", None)
    payload = _project_install(install, asset, writer=True)
    await session.commit()
    return payload


async def uninstall_live_install(session: AsyncSession, install_id: int, user) -> dict:
    logger.info(f"power_market.uninstall_live_install | id={install_id}")
    tenant_id = _assert_writer(user, message=MSG_INSTALL_READONLY)
    install, _asset = await _load_live_pair(session, tenant_id, install_id)
    iid, aid, host = int(install.id), int(install.asset_id), install.host
    install.deleted_at = datetime.now(timezone.utc)
    install.updated_by = getattr(user, "username", None)
    await session.commit()
    await emit_market_event(
        session, MARKET_UNINSTALLED, tenant_id=tenant_id,
        actor_user_id=getattr(user, "id", None),
        role=getattr(user, "tenant_role", None) or getattr(user, "role", None),
        props={"host": host},
    )
    return {"id": iid, "asset_id": aid, "host": host, "deleted": True}


async def _load_live_pair(session: AsyncSession, tenant_id: int, install_id: int):
    row = (await session.execute(
        select(CapabilityInstall, CapabilityAsset)
        .join(CapabilityAsset, CapabilityAsset.id == CapabilityInstall.asset_id)
        .where(
            CapabilityInstall.id == int(install_id),
            CapabilityInstall.tenant_id == tenant_id,
            CapabilityInstall.deleted_at.is_(None),
        )
    )).first()
    if row is None:
        raise NotFoundException("安装行")
    return row


def _flags_locked(asset: CapabilityAsset) -> bool:
    if getattr(asset, "deleted_at", None) is not None:
        return True
    return (asset.status or "") == "blacklist"


def _is_delisted(asset: CapabilityAsset) -> bool:
    return (asset.listing_state or "") not in LISTING_VISIBLE


def _project_install(install: CapabilityInstall, asset: CapabilityAsset, *, writer: bool) -> dict:
    locked = _flags_locked(asset)
    delisted = _is_delisted(asset)
    listed = (asset.listing_state or "") == "listed"
    return {
        "id": int(install.id),
        "tenant_id": int(install.tenant_id),
        "asset_id": int(install.asset_id),
        "asset_name": asset.name,
        "asset_title": asset.title or asset.name,
        "asset_type": _to_public_asset_type(asset.asset_type),
        "host": install.host,
        "enabled": int(install.enabled or 0),
        "trusted": int(install.trusted or 0),
        "listing_state": asset.listing_state,
        "delisted": delisted,
        "delisted_label": MSG_DELISTED if delisted else None,
        "flags_locked": locked,
        "can_change_flags": bool(writer) and not locked,
        "can_uninstall": bool(writer),
        "resubscribe_allowed": bool(writer) and listed and not locked,
        "resubscribe_hint": MSG_DELISTED_RESUBSCRIBE if delisted else None,
        "created_at": install.created_at.isoformat() if install.created_at else None,
    }
