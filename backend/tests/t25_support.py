"""T-25 夹具：租户经办绑定 + 安装行计数。34.9 未声明 ≠ 34.10 已声明零项。"""
from __future__ import annotations

import asyncio

from fastapi import Depends, Request
from sqlalchemy import func, select

from backend.app.api.deps import CurrentUser, _bearer, get_current_user
from backend.tests.fr33_support import fr33_asset, seed_rows
from platform_core.db import get_async_db
from platform_core.models.capability import CapabilityAsset, CapabilityInstall
from platform_core.models.tenant import Tenant


def seed_tenant(db_session, slug: str = "t25-co") -> int:
    async def _go():
        async with db_session() as s:
            row = Tenant(slug=slug, name=slug)
            s.add(row)
            await s.commit()
            return int(row.id)

    return asyncio.run(_go())


def bind_actor(
    app,
    *,
    role: str,
    tenant_id: int | None,
    tenant_role: str | None,
    is_platform_admin: bool = False,
) -> None:
    async def _override(
        request: Request,
        credentials=Depends(_bearer),
        session=Depends(get_async_db),
    ):
        if credentials is not None and getattr(credentials, "credentials", ""):
            from backend.tests.conftest import _current_user_override

            return await _current_user_override(
                request, credentials, session, default_role=None,
            )
        return CurrentUser(
            id=1, username=f"t25-{role}", role=role,
            tenant_id=tenant_id, tenant_role=tenant_role,
            is_platform_admin=is_platform_admin,
        )

    app.dependency_overrides[get_current_user] = _override


def live_installs(db_session) -> list[CapabilityInstall]:
    async def _go():
        async with db_session() as s:
            rows = (await s.execute(
                select(CapabilityInstall).where(CapabilityInstall.deleted_at.is_(None))
            )).scalars().all()
            return list(rows)

    return asyncio.run(_go())


def live_install_count(db_session) -> int:
    async def _go():
        async with db_session() as s:
            n = (await s.execute(
                select(func.count()).select_from(CapabilityInstall).where(
                    CapabilityInstall.deleted_at.is_(None),
                )
            )).scalar_one()
            return int(n)

    return asyncio.run(_go())


def seed_listed(db_session, **kwargs) -> None:
    seed_rows(db_session, [fr33_asset(**kwargs)])


def subscribe_url(asset_type: str, name: str) -> str:
    return f"/api/v1/capabilities/{asset_type}/{name}/subscribe"


def public_subscribe_url(asset_type: str, name: str) -> str:
    return f"/api/v1/public/capabilities/{asset_type}/{name}/subscribe"


def asset_id_of(db_session, name: str) -> int:
    async def _go():
        async with db_session() as s:
            row = (await s.execute(
                select(CapabilityAsset).where(CapabilityAsset.name == name)
            )).scalar_one()
            return int(row.id)

    return asyncio.run(_go())
