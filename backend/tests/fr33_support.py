"""T-23 夹具：FR-33 查询侧闸行 + 六种不可见行。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from platform_core.models.capability import CapabilityAsset, CapabilityComponent


def fr33_asset(**kwargs) -> CapabilityAsset:
    row = dict(
        asset_type="skill",
        category="cat-a",
        listing_state="listed",
        status="stable",
        license="MIT",
        public_license_override=0,
        title="",
        description="说明",
        source_url="https://example.invalid/src",
        source_author="qa",
    )
    row.update(kwargs)
    return CapabilityAsset(**row)


def seed_rows(db_session, rows: list) -> None:
    async def _go():
        async with db_session() as s:
            s.add_all(rows)
            await s.commit()

    asyncio.run(_go())


def gwt_33_2_rows(*, prefix: str = "g332") -> list[CapabilityAsset]:
    """六种组合各一行：仅预告+已发布、已上架+推荐应出现。"""
    return [
        fr33_asset(name=f"{prefix}-soon", listing_state="coming_soon", title="预告卡"),
        fr33_asset(name=f"{prefix}-rec", status="recommended", title="推荐卡"),
        fr33_asset(name=f"{prefix}-exp", status="experimental"),
        fr33_asset(name=f"{prefix}-unlist", listing_state="unlisted"),
        fr33_asset(name=f"{prefix}-black", status="blacklist"),
        fr33_asset(name=f"{prefix}-nolic", license="NOASSERTION"),
    ]


def gwt_33_hidden_tail(*, prefix: str) -> list[CapabilityAsset]:
    """插在过闸行之后（更大 id），id DESC 时若先 LIMIT 再滤会把它们排进第 1 页。"""
    return [
        fr33_asset(name=f"{prefix}-unlist", listing_state="unlisted"),
        fr33_asset(name=f"{prefix}-black", status="blacklist"),
        fr33_asset(name=f"{prefix}-nolic", license="NOASSERTION"),
        fr33_asset(name=f"{prefix}-exp", status="experimental"),
        fr33_asset(name=f"{prefix}-test", status="testing"),
        fr33_asset(name=f"{prefix}-dep", status="deprecated"),
    ]


def gwt_33_4_rows(*, page_size: int = 20) -> list[CapabilityAsset]:
    visible = [
        fr33_asset(name=f"g334-vis-{i:02d}", title=f"可见{i}")
        for i in range(page_size)
    ]
    return visible + gwt_33_hidden_tail(prefix="g334")


def gwt_33_5_rows(*, page_size: int = 20, extra: int = 5) -> list[CapabilityAsset]:
    visible = [
        fr33_asset(name=f"g335-vis-{i:02d}", title=f"可见{i}")
        for i in range(page_size + extra)
    ]
    return visible + gwt_33_hidden_tail(prefix="g335")


def seed_include_parent(db_session, *, parent: str, children: list[dict]) -> None:
    async def _go():
        async with db_session() as s:
            plug = fr33_asset(
                asset_type="plugin", name=parent, category="cat-p", title=parent,
            )
            s.add(plug)
            await s.flush()
            child_rows = []
            for spec in children:
                child_rows.append(fr33_asset(
                    asset_type=spec.get("asset_type", "skill"),
                    name=spec["name"],
                    listing_state=spec.get("listing_state", "listed"),
                    status=spec.get("status", "stable"),
                    license=spec.get("license", "MIT"),
                    deleted_at=spec.get("deleted_at"),
                    title=spec["name"],
                ))
            s.add_all(child_rows)
            await s.flush()
            for child in child_rows:
                s.add(CapabilityComponent(
                    parent_asset_id=plug.id,
                    child_asset_id=child.id,
                    role="bundled_skill",
                ))
            await s.commit()

    asyncio.run(_go())


def utcnow():
    return datetime.now(timezone.utc)
