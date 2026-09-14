"""T-20 / FR-M32：按登录名停用/筛选已停用/恢复；租户 404；种子 admin 不可删。"""
from __future__ import annotations

import asyncio

from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

USERS = "/api/v1/admin/users"
GHOST = "/api/v1/admin/tenants"


def _add_user(db_session, *, username: str, email: str, tenant_id: int,
              is_active: bool = True, is_platform_admin: bool = False) -> int:
    async def _go():
        async with db_session() as s:
            row = User(
                username=username, email=email, password_hash="x",
                role="admin" if is_platform_admin else "operator",
                is_admin=is_platform_admin, is_platform_admin=is_platform_admin,
                tenant_id=tenant_id,
                tenant_role=None if is_platform_admin else "operator",
                is_active=is_active,
            )
            s.add(row)
            await s.commit()
            await s.refresh(row)
            return int(row.id)

    return asyncio.run(_go())


def test_gwt_m32_1_disable_by_login_name(db_client, db_session):
    from backend.utils.auth import get_password_hash

    pa = make_platform_admin_headers(db_session)
    async def _seed():
        async with db_session() as s:
            t = Tenant(slug="m32-1", name="M32")
            s.add(t)
            await s.flush()
            hashed = await asyncio.to_thread(get_password_hash, "Passw0rd!")
            u = User(
                username="stop-me", email="stop-me@x.co", password_hash=hashed,
                role="operator", tenant_id=t.id, tenant_role="operator", is_active=True,
            )
            s.add(u)
            await s.commit()
            await s.refresh(u)
            return int(u.id)

    uid = asyncio.run(_seed())
    found = db_client.get(f"{USERS}?q=stop-me", headers=pa)
    assert found.status_code == 200, found.text
    items = found.json()["data"]["items"]
    assert any(u["username"] == "stop-me" for u in items)
    patched = db_client.patch(f"{USERS}/{uid}", headers=pa, json={"is_active": False})
    assert patched.status_code == 200, patched.text
    assert patched.json()["data"]["is_active"] is False
    login = db_client.post("/api/v1/auth/login", json={"username": "stop-me", "password": "Passw0rd!"})
    assert login.status_code == 401


def test_gwt_m32_2_filter_disabled_empty(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    resp = db_client.get(f"{USERS}?status=disabled", headers=pa)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["items"] == []
    assert resp.json()["data"]["total"] == 0


def test_gwt_m32_3_tenant_users_write_404(db_client, db_session):
    owner, _ = make_tenant_owner_headers(db_session, slug="m32-3")
    ghost = db_client.get(GHOST, headers=owner)
    listed = db_client.get(USERS, headers=owner)
    assert listed.status_code == ghost.status_code == 404
    assert listed.json()["code"] == "HTTP_404"
    patched = db_client.patch(f"{USERS}/1", headers=owner, json={"is_active": False})
    assert patched.status_code == 404


def test_gwt_m32_4_restore_disabled_can_login(db_client, db_session):
    from backend.utils.auth import get_password_hash

    pa = make_platform_admin_headers(db_session)

    async def _seed():
        async with db_session() as s:
            t = Tenant(slug="m32-4", name="M32-4")
            s.add(t)
            await s.flush()
            hashed = await asyncio.to_thread(get_password_hash, "Passw0rd!")
            u = User(
                username="back-me", email="back-me@x.co", password_hash=hashed,
                role="operator", tenant_id=t.id, tenant_role="operator", is_active=False,
            )
            s.add(u)
            await s.commit()
            await s.refresh(u)
            return int(u.id)

    uid = asyncio.run(_seed())
    restored = db_client.post(f"{USERS}/{uid}/restore", headers=pa)
    assert restored.status_code == 200, restored.text
    assert restored.json()["data"]["is_active"] is True
    login = db_client.post("/api/v1/auth/login", json={"username": "back-me", "password": "Passw0rd!"})
    assert login.status_code == 200, login.text
    events = db_client.get(
        "/api/v1/product-events", headers=pa, params={"event_name": "user_restored"},
    )
    assert any(
        (r.get("props") or {}).get("restored_user_id") == uid
        for r in events.json()["data"]["items"]
    )
