"""T-09 FR-U12/U15：租户打上架/扫描/平台渠道/RBAC = 404 同形，超管仍可保存。"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from backend.tests.fr33_support import fr33_asset, seed_rows
from platform_core.models.capability import CapabilityAsset
from platform_core.models.operation_log import OperationLog
from platform_core.models.role import Role

LISTING = "/api/v1/capabilities/skill/{}/listing"
SYNC_HUB = "/api/v1/capabilities/sync-agents-hub"
SCAN_SKILLS = "/api/v1/skills/scan"
SOURCES = "/api/v1/capabilities/sources"
CHANNEL_CFG = "/api/v1/newapi/channels/3/config"
ROLES = "/api/v1/rbac/roles"
SORRY = "抱歉您没有权限"


def _denied_logs(db_session):
    async def _go():
        async with db_session() as s:
            return list((await s.execute(
                select(OperationLog).where(OperationLog.action == "authz.denied")
            )).scalars().all())

    return asyncio.run(_go())


def _assert_missing_shape(resp, ghost):
    assert resp.status_code == ghost.status_code == 404, resp.text
    body, other = resp.json(), ghost.json()
    assert body["code"] == other["code"] == "HTTP_404"
    assert body["message"] == other["message"] == "Not Found"
    assert "FORBIDDEN" not in body["code"]
    assert SORRY not in resp.text
    assert "抱歉" not in resp.text


def test_gwt_u12_1_platform_admin_can_list(db_client, platform_admin_client, db_session):
    seed_rows(db_session, [fr33_asset(name="u121-row", listing_state="unlisted")])
    resp = platform_admin_client.patch(
        LISTING.format("u121-row"),
        json={"listing_state": "listed", "confirm": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["listing_state"] == "listed"


def test_gwt_u12_2_tenant_admin_listing_scan_404(
    db_client, admin_client, db_session,
):
    seed_rows(db_session, [fr33_asset(name="u122-row", listing_state="unlisted")])
    ghost = admin_client.get("/api/v1/admin/tenants")
    listing = admin_client.patch(
        LISTING.format("u122-row"), json={"listing_state": "listed"},
    )
    _assert_missing_shape(listing, ghost)
    scan = admin_client.post(SYNC_HUB)
    _assert_missing_shape(scan, ghost)
    # K4：scan-experts 已整条退役（路由表里不存在），对任何调用者都是路由级
    # 404——不再是这条用例要验证的"平台写面越权守卫"命中，挪出遍历列表。
    skills = admin_client.post(SCAN_SKILLS)
    _assert_missing_shape(skills, ghost)
    sources = admin_client.get(SOURCES)
    _assert_missing_shape(sources, ghost)
    row = _asset(db_session, "u122-row")
    assert row.listing_state == "unlisted"


def test_gwt_u12_3_tenant_admin_channel_and_listing_leftover(
    db_client, admin_client, db_session,
):
    seed_rows(db_session, [fr33_asset(name="u123-row", listing_state="unlisted")])
    ghost = admin_client.get("/api/v1/admin/tenants")
    listing = admin_client.patch(
        LISTING.format("u123-row"), json={"listing_state": "listed"},
    )
    _assert_missing_shape(listing, ghost)
    channel = admin_client.put(CHANNEL_CFG, json={
        "limit_quota": 10, "window_hours": 24, "cooldown_seconds": 60,
    })
    _assert_missing_shape(channel, ghost)
    row = _asset(db_session, "u123-row")
    assert row.listing_state == "unlisted"
    logs = _denied_logs(db_session)
    assert logs
    targets = " ".join(str(item.target) for item in logs)
    assert "listing" in targets or "scan" in targets or "config" in targets or "rbac" in targets or "newapi" in targets


def test_gwt_u15_1_superadmin_list_save_rbac(db_client, platform_admin_client, db_session):
    _seed_roles(db_session)
    listed = platform_admin_client.get(ROLES)
    assert listed.status_code == 200, listed.text
    roles = listed.json()["data"]["roles"]
    admin = next(r for r in roles if r["role_key"] == "admin")
    perms = list(admin["permissions"])
    wanted = list(dict.fromkeys([*perms, "menu:logs"]))
    saved = platform_admin_client.put(
        f"{ROLES}/admin", json={"permissions": wanted},
    )
    assert saved.status_code == 200, saved.text
    refresh = platform_admin_client.get(ROLES)
    admin_after = next(
        r for r in refresh.json()["data"]["roles"] if r["role_key"] == "admin"
    )
    assert set(admin_after["permissions"]) == set(wanted)
    restore = platform_admin_client.put(
        f"{ROLES}/admin", json={"permissions": perms},
    )
    assert restore.status_code == 200, restore.text


def test_gwt_u15_3_tenant_admin_rbac_404_no_sorry(db_client, admin_client, db_session):
    _seed_roles(db_session)
    ghost = admin_client.get("/api/v1/admin/tenants")
    listed = admin_client.get(ROLES)
    _assert_missing_shape(listed, ghost)
    assert "roles" not in (listed.json().get("data") or {})
    assert "catalog" not in (listed.json().get("data") or {})
    saved = admin_client.put(
        f"{ROLES}/admin", json={"permissions": ["menu:dashboard"]},
    )
    _assert_missing_shape(saved, ghost)
    logs = _denied_logs(db_session)
    assert logs


def _asset(db_session, name: str) -> CapabilityAsset:
    async def _go():
        async with db_session() as s:
            return (await s.execute(
                select(CapabilityAsset).where(CapabilityAsset.name == name)
            )).scalar_one()

    return asyncio.run(_go())


def _seed_roles(db_session) -> None:
    async def _go():
        async with db_session() as s:
            existing = (await s.execute(
                select(Role).where(Role.role_key == "admin")
            )).scalar_one_or_none()
            if existing is None:
                s.add(Role(
                    role_key="admin", name="管理员",
                    permissions=["menu:dashboard", "menu:skills"],
                    is_builtin=True,
                ))
                await s.commit()

    asyncio.run(_go())
