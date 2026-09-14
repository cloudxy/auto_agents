"""租户 API Key 签发 / 校验 / 吊销。"""
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.exceptions import NotFoundException
from platform_core.logger import get_logger
from platform_core.models.api_key import ApiKey
from platform_core.repository import BaseRepository
from platform_core.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyOut

logger = get_logger("service.api_key")


def _hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


class ApiKeyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = BaseRepository(ApiKey, session)

    async def create_key(self, tenant_id: int, payload: ApiKeyCreate, actor: str) -> ApiKeyCreated:
        logger.info(f"签发 API Key | tenant={tenant_id} name={payload.name}")
        plaintext = "ak_" + secrets.token_urlsafe(32)
        row = ApiKey(
            tenant_id=tenant_id,
            name=payload.name,
            key_prefix=plaintext[:12],
            key_hash=_hash_key(plaintext),
            scopes=payload.scopes,
            expires_at=payload.expires_at,
            note=payload.note,
            created_by=actor,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        base = ApiKeyOut.model_validate(row)
        return ApiKeyCreated(**base.model_dump(), plaintext=plaintext)

    async def list_keys(self, tenant_id: int) -> list[ApiKeyOut]:
        stmt = select(ApiKey).where(ApiKey.tenant_id == tenant_id, ApiKey.deleted_at.is_(None))
        rows = (await self.session.execute(stmt)).scalars().all()
        return [ApiKeyOut.model_validate(r) for r in rows]

    async def revoke(self, tenant_id: int, key_id: int) -> ApiKeyOut:
        row = await self.repo.get_by_id(key_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundException("API Key")
        row.revoked_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(row)
        return ApiKeyOut.model_validate(row)

    async def authenticate(self, plaintext: str) -> Optional[int]:
        """命中返回 tenant_id；无效/过期/吊销返回 None。"""
        if not plaintext:
            return None
        digest = _hash_key(plaintext)
        stmt = select(ApiKey).where(ApiKey.key_hash == digest, ApiKey.deleted_at.is_(None))
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None or row.revoked_at is not None:
            return None
        if row.expires_at is not None and row.expires_at <= datetime.now(timezone.utc):
            return None
        row.last_used_at = datetime.now(timezone.utc)
        try:
            await self.session.commit()
        except Exception:  # noqa: BLE001 鉴权路径更新失败不阻断查询
            await self.session.rollback()
        logger.debug(f"API Key 鉴权通过 | tenant={row.tenant_id} prefix={row.key_prefix}")
        return row.tenant_id
