"""源登记 / 列表 / 第一方回填。url/git 创建失败。"""
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.power_market.identity import _is_first_party_backfill
from backend.services.power_market.types import (
    MSG_GIT_UNSUPPORTED,
    MSG_URL_UNSUPPORTED,
    SOURCE_KIND_CODE,
    SOURCE_KINDS,
    CreateSourceRequest,
)
from platform_core.exceptions import BusinessException, NotFoundException, ValidationException
from platform_core.logger import get_logger
from platform_core.models.capability import CapabilityAsset, CapabilitySource

logger = get_logger("service.power_market")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _project_source(row: CapabilitySource) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "source_kind": row.source_kind,
        "uri": row.uri,
        "is_enabled": int(row.is_enabled or 0),
        "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
        "last_succeeded": int(row.last_succeeded or 0),
        "last_failed": int(row.last_failed or 0),
        "last_error": row.last_error,
    }


class SourceRegistry:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_sources(self) -> dict:
        logger.info("power_market.list_sources")
        rows = (await self.session.execute(
            select(CapabilitySource).where(CapabilitySource.deleted_at.is_(None))
            .order_by(CapabilitySource.id.asc())
        )).scalars().all()
        items = [_project_source(r) for r in rows]
        payload: dict = {"total": len(items), "items": items}
        if not items:
            payload["empty"] = True
            payload["message"] = "还没有源。登记源后才能同步。"
        return payload

    async def get_source(self, name: str) -> CapabilitySource:
        row = (await self.session.execute(
            select(CapabilitySource).where(
                CapabilitySource.name == name,
                CapabilitySource.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundException(resource=f"源 {name}")
        return row

    async def register(self, payload: CreateSourceRequest, *, actor: str) -> dict:
        logger.info(
            f"power_market.register_source | name={payload.name} kind={payload.source_kind}"
        )
        kind = (payload.source_kind or "").strip()
        if kind not in SOURCE_KINDS:
            raise ValidationException("源类型只能是 local/git/url", field="source_kind")
        if kind in ("url", "git"):
            msg = MSG_URL_UNSUPPORTED if kind == "url" else MSG_GIT_UNSUPPORTED
            raise BusinessException(
                message=msg, code=SOURCE_KIND_CODE, status_code=400,
            )
        name = (payload.name or "").strip()
        uri = (payload.uri or "").strip()
        if not name or not uri:
            raise ValidationException("name 与 uri 必填", field="name")
        existing = (await self.session.execute(
            select(CapabilitySource).where(
                CapabilitySource.name == name,
                CapabilitySource.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if existing is not None:
            raise BusinessException(message="源名已存在", code="SOURCE_EXISTS", status_code=409)
        row = CapabilitySource(
            name=name, source_kind=kind, uri=uri, is_enabled=1,
            tenant_id=None, created_by=actor, updated_by=actor,
        )
        self.session.add(row)
        await self.session.flush()
        out = _project_source(row)
        await self.session.commit()
        return out

    async def backfill_first_party(self) -> dict:
        logger.info("power_market.backfill_first_party")
        rows = (await self.session.execute(
            select(CapabilityAsset).where(CapabilityAsset.deleted_at.is_(None))
        )).scalars().all()
        updated = 0
        for row in rows:
            if not _is_first_party_backfill(row):
                continue
            entering = (row.listing_state or "") != "listed"
            row.listing_state = "listed"
            row.writable = 1
            if entering and row.listed_at is None:
                row.listed_at = _utcnow()
            updated += 1
        await self.session.commit()
        return {"updated": updated}

    def resolve_uri(self, source: CapabilitySource) -> Path:
        return Path(source.uri).expanduser()
