"""T-27 夹具：合集边（出处+引用）不是安装礼包。"""
from __future__ import annotations

import asyncio

from backend.tests.fr33_support import fr33_asset
from platform_core.models.capability import CapabilityComponent, CapabilityInstall


def refs_url(asset_type: str, name: str) -> str:
    return f"/api/v1/capabilities/{asset_type}/{name}/references"


def seed_agent_collection(db_session, *, agent: str, children: list[dict]) -> None:
    async def _go():
        async with db_session() as s:
            parent = fr33_asset(
                asset_type="agent", name=agent, category="cat-a", title=agent,
            )
            s.add(parent)
            await s.flush()
            rows = [
                fr33_asset(
                    asset_type=spec.get("asset_type", "skill"),
                    name=spec["name"],
                    listing_state=spec.get("listing_state", "listed"),
                    status=spec.get("status", "stable"),
                    license=spec.get("license", "MIT"),
                    deleted_at=spec.get("deleted_at"),
                    title=spec["name"],
                )
                for spec in children
            ]
            s.add_all(rows)
            await s.flush()
            for child, spec in zip(rows, children):
                s.add(CapabilityComponent(
                    parent_asset_id=parent.id,
                    child_asset_id=child.id,
                    role=spec.get("role", "uses_skill"),
                ))
            await s.commit()

    asyncio.run(_go())


def seed_gift_install(db_session, *, tenant_id: int, name: str) -> None:
    async def _go():
        async with db_session() as s:
            row = fr33_asset(name=name, title=name)
            s.add(row)
            await s.flush()
            s.add(CapabilityInstall(
                tenant_id=tenant_id, asset_id=int(row.id), host="grok",
                enabled=1, trusted=0,
            ))
            await s.commit()

    asyncio.run(_go())
