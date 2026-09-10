"""租户渠道组：分组 + 虚拟令牌。不改平台渠道、不打网关库。"""
import hashlib
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.exceptions import AuthorizationException, BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.models.relay import RelayGroup, RelayToken
from platform_core.schemas.relay import (
    RelayGroupCreate, RelayGroupOut, RelayGroupUpdate, RelayTokenCreate, RelayTokenOut,
)

logger = get_logger("service.relay")

_DEFAULT_GROUP = "default"


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _models_of(row: RelayGroup) -> list[str]:
    raw = row.models_json
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return []


def _group_out(row: RelayGroup) -> RelayGroupOut:
    return RelayGroupOut(
        id=int(row.id),
        name=str(row.name),
        rpm_limit=int(row.rpm_limit or 0),
        tpm_limit=int(row.tpm_limit or 0),
        models=_models_of(row),
        status=str(row.status),
        tenant_id=row.tenant_id,
        created_at=row.created_at,
    )


def _token_status(row: RelayToken) -> str:
    if row.revoked_at is not None:
        return "revoked"
    if row.expires_at is not None and row.expires_at < datetime.now(timezone.utc):
        return "expired"
    return "active"


class RelayService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_groups(self, tenant_id: int) -> list[RelayGroupOut]:
        logger.info(f"列出渠道组 | tenant={tenant_id}")
        rows = (await self.session.execute(
            select(RelayGroup).where(RelayGroup.tenant_id == tenant_id).order_by(RelayGroup.id.asc())
        )).scalars().all()
        if not rows:
            created = await self._ensure_default(tenant_id)
            return [_group_out(created)]
        return [_group_out(r) for r in rows]

    async def create_group(self, tenant_id: int, payload: RelayGroupCreate) -> RelayGroupOut:
        logger.info(f"创建渠道组 | tenant={tenant_id} name={payload.name}")
        existing = (await self.session.execute(
            select(RelayGroup).where(
                RelayGroup.tenant_id == tenant_id, RelayGroup.name == payload.name,
            )
        )).scalar_one_or_none()
        if existing is not None:
            raise BusinessException(message="组名已存在", code="RELAY_GROUP_EXISTS")
        row = RelayGroup(
            tenant_id=tenant_id,
            name=payload.name.strip(),
            rpm_limit=max(0, int(payload.rpm_limit)),
            tpm_limit=max(0, int(payload.tpm_limit)),
            models_json=list(payload.models),
            status="enabled",
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return _group_out(row)

    async def update_group(
        self, tenant_id: int, group_id: int, payload: RelayGroupUpdate,
    ) -> RelayGroupOut:
        logger.info(f"更新渠道组 | tenant={tenant_id} group={group_id}")
        row = await self._owned_group(tenant_id, group_id)
        if payload.name is not None:
            row.name = payload.name.strip()
        if payload.rpm_limit is not None:
            row.rpm_limit = max(0, int(payload.rpm_limit))
        if payload.tpm_limit is not None:
            row.tpm_limit = max(0, int(payload.tpm_limit))
        if payload.models is not None:
            row.models_json = list(payload.models)
        if payload.status is not None:
            if payload.status not in ("enabled", "disabled"):
                raise BusinessException(message="状态只能是 enabled/disabled", code="RELAY_BAD_STATUS")
            row.status = payload.status
        await self.session.commit()
        await self.session.refresh(row)
        return _group_out(row)

    async def list_tokens(self, tenant_id: int) -> list[RelayTokenOut]:
        logger.info(f"列出令牌 | tenant={tenant_id}")
        rows = (await self.session.execute(
            select(RelayToken).where(RelayToken.tenant_id == tenant_id).order_by(RelayToken.id.desc())
        )).scalars().all()
        return [self._token_out(r) for r in rows]

    async def issue_token(self, tenant_id: int, payload: RelayTokenCreate) -> RelayTokenOut:
        logger.info(f"签发令牌 | tenant={tenant_id} group={payload.group_id}")
        group = await self._owned_group(tenant_id, payload.group_id)
        if group.status != "enabled":
            raise BusinessException(message="渠道组已停用", code="RELAY_GROUP_DISABLED")
        raw = "sk-" + secrets.token_urlsafe(32)
        row = RelayToken(
            tenant_id=tenant_id,
            group_id=group.id,
            name=payload.name.strip(),
            key_prefix=raw[:10],
            key_hash=_hash_key(raw),
            quota_tokens=int(payload.quota_tokens),
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        out = self._token_out(row)
        return out.model_copy(update={"plaintext_key": raw})

    async def revoke_token(self, tenant_id: int, token_id: int) -> RelayTokenOut:
        logger.info(f"吊销令牌 | tenant={tenant_id} token={token_id}")
        row = (await self.session.execute(
            select(RelayToken).where(
                RelayToken.id == token_id, RelayToken.tenant_id == tenant_id,
            )
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundException("令牌")
        if row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            await self.session.commit()
            await self.session.refresh(row)
        return self._token_out(row)

    async def _ensure_default(self, tenant_id: int) -> RelayGroup:
        row = RelayGroup(
            tenant_id=tenant_id, name=_DEFAULT_GROUP,
            rpm_limit=0, tpm_limit=0, models_json=[], status="enabled",
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def _owned_group(self, tenant_id: int, group_id: int) -> RelayGroup:
        row = await self.session.get(RelayGroup, group_id)
        if row is None or int(row.tenant_id or 0) != int(tenant_id):
            raise NotFoundException("渠道组")
        return row

    @staticmethod
    def _token_out(row: RelayToken) -> RelayTokenOut:
        return RelayTokenOut(
            id=int(row.id),
            group_id=int(row.group_id),
            name=str(row.name),
            key_prefix=str(row.key_prefix),
            quota_tokens=int(row.quota_tokens),
            used_tokens=int(row.used_tokens or 0),
            status=_token_status(row),
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            created_at=row.created_at,
            plaintext_key=None,
        )


def require_tenant_id(tenant_id: int | None) -> int:
    logger.debug("校验企业空间")
    if tenant_id is None:
        raise AuthorizationException(message="需要企业空间")
    return int(tenant_id)
