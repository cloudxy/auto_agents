"""T-28 FR-37 / FR-40：上架写、listed_at、无 MCP=unknown 可 listed、dev-team 句。"""
import asyncio

from sqlalchemy import select

from backend.tests.fr33_support import fr33_asset, seed_rows
from backend.tests.t25_support import seed_listed
from platform_core.models.capability import (
    CapabilityAsset,
    CapabilityComponent,
    CapabilityPlugin,
)

_LISTING = "/api/v1/capabilities/{}/{}/listing"
_VERIFY = "/api/v1/capabilities/plugins/{}/verify"
_MERGED = "已合并，不可上架"
_CONFIRM = "将把第三方「{name}」标为已上架，商店会对访客可见。确认上架？"


def _listing_url(asset_type: str, name: str) -> str:
    return _LISTING.format(asset_type, name)


def _query_all(db_session, stmt):
    async def _go():
        async with db_session() as s:
            return list((await s.execute(stmt)).scalars().all())
    return asyncio.run(_go())


def _seed_plugin(db_session, name: str, **kwargs) -> None:
    mcp = kwargs.pop("mcp_servers", {})
    health = kwargs.pop("health_status", "unknown")

    async def _go():
        async with db_session() as s:
            asset = fr33_asset(
                asset_type="plugin", name=name, listing_state="unlisted",
                **kwargs,
            )
            s.add(asset)
            await s.flush()
            s.add(CapabilityPlugin(
                asset_id=asset.id, mcp_servers=mcp, health_status=health,
            ))
            await s.commit()

    asyncio.run(_go())


def _seed_merged(db_session) -> None:
    async def _go():
        async with db_session() as s:
            parent = fr33_asset(
                asset_type="plugin", name="dev-team", listing_state="unlisted",
                category="cat-p",
            )
            child = fr33_asset(name="kept-child", listing_state="listed")
            s.add_all([parent, child])
            await s.flush()
            s.add(CapabilityComponent(
                parent_asset_id=parent.id, child_asset_id=child.id,
                role="bundled_skill",
            ))
            await s.commit()

    asyncio.run(_go())


def test_gwt_37_3_tenant_admin_cannot_list(db_client, admin_client, db_session):
    seed_listed(db_session, name="g373-row", listing_state="unlisted")
    resp = admin_client.patch(
        _listing_url("skill", "g373-row"), json={"listing_state": "listed"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"
    row = _query_all(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "g373-row",
    ))[0]
    assert row.listing_state == "unlisted"


def test_gwt_37_3_viewer_cannot_list(db_client, viewer_client, db_session):
    seed_listed(db_session, name="g373-view", listing_state="unlisted")
    resp = viewer_client.patch(
        _listing_url("skill", "g373-view"), json={"listing_state": "listed"},
    )
    assert resp.status_code == 403
    row = _query_all(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "g373-view",
    ))[0]
    assert row.listing_state == "unlisted"


def test_gwt_37_4_dev_team_merged_children_keep(
    db_client, platform_admin_client, db_session,
):
    _seed_merged(db_session)
    resp = platform_admin_client.patch(
        _listing_url("plugin", "dev-team"), json={"listing_state": "listed"},
    )
    assert resp.status_code == 400
    assert _MERGED in resp.json()["message"]
    parent = _query_all(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "dev-team",
    ))[0]
    child = _query_all(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "kept-child",
    ))[0]
    assert parent.listing_state == "unlisted"
    assert child.listing_state == "listed"


def test_gwt_37_6_listed_at_survives_unlist(
    db_client, platform_admin_client, db_session,
):
    seed_listed(db_session, name="g376-row", listing_state="unlisted")
    listed = platform_admin_client.patch(
        _listing_url("skill", "g376-row"), json={"listing_state": "listed"},
    )
    assert listed.status_code == 200, listed.text
    stamp = listed.json()["data"]["listed_at"]
    assert stamp
    unlisted = platform_admin_client.patch(
        _listing_url("skill", "g376-row"), json={"listing_state": "unlisted"},
    )
    assert unlisted.status_code == 200, unlisted.text
    data = unlisted.json()["data"]
    assert data["listing_state"] == "unlisted"
    assert data["listed_at"] == stamp
    row = _query_all(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "g376-row",
    ))[0]
    assert row.listing_state == "unlisted"
    assert row.listed_at is not None


def test_gwt_40_1_no_mcp_unknown_can_list(
    db_client, platform_admin_client, db_session,
):
    _seed_plugin(db_session, "no-mcp-plug")
    verify = platform_admin_client.post(_VERIFY.format("no-mcp-plug"))
    assert verify.status_code == 200, verify.text
    assert verify.json()["data"]["health"] == "unknown"
    listed = platform_admin_client.patch(
        _listing_url("plugin", "no-mcp-plug"), json={"listing_state": "listed"},
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["listing_state"] == "listed"
    detail = platform_admin_client.get("/api/v1/capabilities/plugins/no-mcp-plug")
    assert detail.status_code == 200
    assert detail.json()["data"]["health_status"] == "unknown"


def test_gwt_40_3_tenant_verify_forbidden(
    db_client, admin_client, db_session,
):
    _seed_plugin(db_session, "g403-plug")
    resp = admin_client.post(_VERIFY.format("g403-plug"))
    assert resp.status_code == 403
    plugin = _query_all(db_session, select(CapabilityPlugin))[0]
    assert plugin.health_status == "unknown"


def test_third_party_list_needs_confirm(
    db_client, platform_admin_client, db_session,
):
    seed_rows(db_session, [fr33_asset(
        name="third-a", listing_state="unlisted",
        source_type="network_imported",
    )])
    denied = platform_admin_client.patch(
        _listing_url("skill", "third-a"), json={"listing_state": "listed"},
    )
    assert denied.status_code == 409
    assert _CONFIRM.format(name="third-a") in denied.json()["message"]
    ok = platform_admin_client.patch(
        _listing_url("skill", "third-a"),
        json={"listing_state": "listed", "confirm": True},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["listing_state"] == "listed"


def test_blacklist_cannot_list(db_client, platform_admin_client, db_session):
    seed_listed(
        db_session, name="black-a", listing_state="unlisted", status="blacklist",
    )
    resp = platform_admin_client.patch(
        _listing_url("skill", "black-a"), json={"listing_state": "listed"},
    )
    assert resp.status_code == 409
    row = _query_all(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "black-a",
    ))[0]
    assert row.listing_state == "unlisted"
    assert row.status == "blacklist"


def test_list_payload_has_listing_fields(db_client, platform_admin_client, db_session):
    seed_listed(db_session, name="cat-a", listing_state="unlisted")
    resp = platform_admin_client.get("/api/v1/capabilities", params={"type": "skill"})
    assert resp.status_code == 200, resp.text
    item = next(i for i in resp.json()["data"]["items"] if i["name"] == "cat-a")
    assert item["listing_state"] == "unlisted"
    assert "listed_at" in item
    assert "source_type" in item
