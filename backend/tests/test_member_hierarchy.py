"""成员管理分级（审计 R1-1 / B1-1 / BUG-01 回归）

口径（D23-A 临时最严）：
- owner 可管理 admin/operator/viewer；admin 只能管理 operator/viewer
- owner 只能由 owner 自己管理；任何人都不能经成员接口产生 owner
- 平台超管行对租户侧不可见：列表不出现，改/删/重置密码一律 404 同形
"""
from __future__ import annotations

import asyncio

from conftest import make_tenant_owner_headers
from platform_core.models.user import User
from sqlalchemy import select

MEMBERS = "/api/v1/members"


def _seed_user(db_session, tid: int, username: str, *, tenant_role: str | None,
               role: str = "viewer", platform: bool = False, token: bool = True):
    """落一名成员；返回 (headers|None, user_id)"""
    from backend.services.auth_service import AuthService

    async def _go():
        async with db_session() as s:
            s.add(User(
                username=username, email=f"{username}@x.co", password_hash="orig-hash",
                role=role, tenant_id=tid, tenant_role=tenant_role, is_active=True,
                is_platform_admin=platform, is_admin=role == "admin",
            ))
            await s.commit()
            u = (await s.execute(select(User).where(User.username == username))).scalar_one()
            if not token:
                return None, int(u.id)
            tok = await AuthService(s).create_token({
                "id": u.id, "username": u.username, "is_admin": role == "admin", "role": role,
                "tenant_id": tid, "tenant_role": tenant_role, "is_platform_admin": platform,
            })
            return {"Authorization": f"Bearer {tok.access_token}"}, int(u.id)

    return asyncio.run(_go())


def _hash(db_session, uid: int) -> str:
    async def _go():
        async with db_session() as s:
            return (await s.execute(select(User.password_hash).where(User.id == uid))).scalar_one()
    return asyncio.run(_go())


def _body(username: str, tenant_role: str) -> dict:
    return {"username": username, "email": f"{username}@x.co",
            "password": "Passw0rd!", "tenant_role": tenant_role}


def _owner_id(db_session, tid: int) -> int:
    async def _go():
        async with db_session() as s:
            return (await s.execute(select(User.id).where(
                User.tenant_id == tid, User.tenant_role == "owner"))).scalar_one()
    return asyncio.run(_go())


def test_admin_cannot_create_admin_or_owner(db_client, db_session):
    _owner, tid = make_tenant_owner_headers(db_session, slug="h-create")
    admin, _ = _seed_user(db_session, tid, "h-admin", tenant_role="admin", role="admin")
    resp = db_client.post(MEMBERS, headers=admin, json=_body("h-new-admin", "admin"))
    assert resp.status_code == 403
    assert resp.json()["code"] == "MEMBER_HIERARCHY"
    resp = db_client.post(MEMBERS, headers=admin, json=_body("h-new-owner", "owner"))
    assert resp.status_code == 422
    ok = db_client.post(MEMBERS, headers=admin, json=_body("h-new-op", "operator"))
    assert ok.status_code in (200, 201), ok.text


def test_owner_cannot_create_second_owner(db_client, db_session):
    owner, _tid = make_tenant_owner_headers(db_session, slug="h-2owner")
    resp = db_client.post(MEMBERS, headers=owner, json=_body("h-owner2", "owner"))
    assert resp.status_code == 422
    assert resp.json()["data"]["field"] == "tenant_role"
    ok = db_client.post(MEMBERS, headers=owner, json=_body("h-admin2", "admin"))
    assert ok.status_code in (200, 201), ok.text


def test_admin_cannot_reset_owner_password(db_client, db_session):
    """原漏洞：admin 重置 owner 密码后即可登录接管企业"""
    _owner, tid = make_tenant_owner_headers(db_session, slug="h-reset")
    admin, _ = _seed_user(db_session, tid, "h-admin-r", tenant_role="admin", role="admin")
    oid = _owner_id(db_session, tid)
    before = _hash(db_session, oid)
    resp = db_client.post(f"{MEMBERS}/{oid}/reset-password", headers=admin,
                          json={"new_password": "Hijack123!"})
    assert resp.status_code == 403
    assert _hash(db_session, oid) == before


def test_admin_cannot_manage_peer_admin(db_client, db_session):
    _owner, tid = make_tenant_owner_headers(db_session, slug="h-peer")
    admin, _ = _seed_user(db_session, tid, "h-admin-a", tenant_role="admin", role="admin")
    _, peer = _seed_user(db_session, tid, "h-admin-b", tenant_role="admin", role="admin",
                         token=False)
    assert db_client.post(f"{MEMBERS}/{peer}/reset-password", headers=admin,
                          json={"new_password": "Hijack123!"}).status_code == 403
    assert db_client.patch(f"{MEMBERS}/{peer}", headers=admin,
                           json={"is_active": False}).status_code == 403
    assert db_client.delete(f"{MEMBERS}/{peer}", headers=admin).status_code == 403
    assert _hash(db_session, peer) == "orig-hash"


def test_admin_cannot_promote_to_admin(db_client, db_session):
    _owner, tid = make_tenant_owner_headers(db_session, slug="h-promote")
    admin, _ = _seed_user(db_session, tid, "h-admin-p", tenant_role="admin", role="admin")
    _, viewer = _seed_user(db_session, tid, "h-viewer-p", tenant_role="viewer", token=False)
    resp = db_client.patch(f"{MEMBERS}/{viewer}", headers=admin, json={"tenant_role": "admin"})
    assert resp.status_code == 403
    resp = db_client.patch(f"{MEMBERS}/{viewer}", headers=admin, json={"tenant_role": "owner"})
    assert resp.status_code == 422


def test_admin_manages_operator_and_viewer(db_client, db_session):
    """正常路径不被误伤：admin 可重置/改角色/禁用/删除 operator 与 viewer"""
    _owner, tid = make_tenant_owner_headers(db_session, slug="h-ok")
    admin, _ = _seed_user(db_session, tid, "h-admin-ok", tenant_role="admin", role="admin")
    _, op = _seed_user(db_session, tid, "h-op-ok", tenant_role="operator", token=False)
    _, viewer = _seed_user(db_session, tid, "h-viewer-ok", tenant_role="viewer", token=False)
    assert db_client.post(f"{MEMBERS}/{op}/reset-password", headers=admin,
                          json={"new_password": "NewPass1!"}).status_code == 200
    assert _hash(db_session, op) != "orig-hash"
    assert db_client.patch(f"{MEMBERS}/{viewer}", headers=admin,
                           json={"tenant_role": "operator"}).status_code == 200
    assert db_client.patch(f"{MEMBERS}/{op}", headers=admin,
                           json={"is_active": False}).status_code == 200
    assert db_client.delete(f"{MEMBERS}/{viewer}", headers=admin).status_code == 200


def test_owner_manages_admin(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="h-owner-ok")
    _, adm = _seed_user(db_session, tid, "h-adm-o", tenant_role="admin", role="admin",
                        token=False)
    assert db_client.post(f"{MEMBERS}/{adm}/reset-password", headers=owner,
                          json={"new_password": "NewPass1!"}).status_code == 200
    assert db_client.patch(f"{MEMBERS}/{adm}", headers=owner,
                           json={"tenant_role": "viewer"}).status_code == 200


def test_platform_admin_invisible_to_same_tenant_admin(db_client, db_session):
    """B1-1：超管挂在某租户下时，该租户 admin 不得看见、重置、禁用或删除超管"""
    owner, tid = make_tenant_owner_headers(db_session, slug="h-platform")
    admin, _ = _seed_user(db_session, tid, "h-admin-x", tenant_role="admin", role="admin")
    _, root = _seed_user(db_session, tid, "h-root", tenant_role=None, role="admin",
                         platform=True, token=False)
    for headers in (owner, admin):
        listed = db_client.get(MEMBERS, headers=headers)
        assert listed.status_code == 200
        assert root not in [m["id"] for m in listed.json()["data"]]
        assert db_client.post(f"{MEMBERS}/{root}/reset-password", headers=headers,
                              json={"new_password": "Hijack123!"}).status_code == 404
        assert db_client.patch(f"{MEMBERS}/{root}", headers=headers,
                               json={"is_active": False}).status_code == 404
        assert db_client.delete(f"{MEMBERS}/{root}", headers=headers).status_code == 404
    assert _hash(db_session, root) == "orig-hash"


def test_legacy_admin_without_tenant_role_is_protected(db_client, db_session):
    """历史行 tenant_role 为空但 role=admin：按 admin 对待，admin 不可管理"""
    _owner, tid = make_tenant_owner_headers(db_session, slug="h-legacy")
    admin, _ = _seed_user(db_session, tid, "h-admin-l", tenant_role="admin", role="admin")
    _, legacy = _seed_user(db_session, tid, "h-legacy", tenant_role=None, role="admin",
                           token=False)
    assert db_client.post(f"{MEMBERS}/{legacy}/reset-password", headers=admin,
                          json={"new_password": "Hijack123!"}).status_code == 403
