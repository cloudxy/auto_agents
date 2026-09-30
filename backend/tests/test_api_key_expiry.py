"""API Key 过期判定（审计 BUG-43 延伸）：库里的 expires_at 是 UTC naive，
原先与带时区的 now 比较直接 TypeError，设了有效期的 Key 一律鉴权 500"""
from datetime import timedelta

import pytest

from platform_core.schemas.api_key import ApiKeyCreate
from platform_core.timeutil import utcnow


@pytest.mark.asyncio
async def test_key_with_future_expiry_authenticates_and_expired_key_rejected(db_session):
    from backend.services.api_key_service import ApiKeyService

    async with db_session() as s:
        svc = ApiKeyService(s)
        live = await svc.create_key(1, ApiKeyCreate(name="live", expires_at=utcnow() + timedelta(days=1)), "t")
        dead = await svc.create_key(1, ApiKeyCreate(name="dead", expires_at=utcnow() - timedelta(minutes=1)), "t")
    async with db_session() as s:
        svc = ApiKeyService(s)
        assert await svc.authenticate(live.plaintext) == 1
        assert await svc.authenticate(dead.plaintext) is None
