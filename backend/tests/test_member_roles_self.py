"""成员角色派生与自身保护（审计 BUG-05 / BUG-06 / QA-B1-4 回归）"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.user import User
from platform_core.roles import derive_legacy_role, tenant_role_from_legacy

MEMBERS = "/api/v1/members"


def _row(db_session, username: str) -> User:
    async def _go():
        async with db_session() as s:
            return (await s.execute(select(User).where(User.username == username))).scalar_one()
    return asyncio.run(_go())


def test_derivation_table():
    assert [derive_legacy_role(r) for r in ("owner", "admin", "operator", "viewer", None, "x")] == [
        "admin", "admin", "operator", "viewer", "viewer", "viewer"]
    assert tenant_role_from_legacy("admin") == "admin"
    assert tenant_role_from_legacy("owner") == "viewer"  # 永不经此产生 owner


def test_operator_member_can_operate(db_client, db_session):
    """原先 operator 被写成 role=viewer：所有 require_operator 端点 403"""
    owner, tid = make_tenant_owner_headers(db_session, slug="role-op")
    created = db_client.post(MEMBERS, headers=owner, json={
        "username": "role-op-user", "email": "role-op@x.co", "password": "Passw0rd!", "tenant_role": "operator"})
    assert created.status_code in (200, 201), created.text
    assert _row(db_session, "role-op-user").role == "operator"
    login = db_client.post("/api/v1/auth/login", json={"username": "role-op-user", "password": "Passw0rd!"})
    token = login.json()["data"]["access_token"]
    resp = db_client.get("/api/v1/api-keys", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text


def test_cannot_disable_or_change_own_role(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="role-self")
    db_client.post(MEMBERS, headers=owner, json={
        "username": "role-self-admin", "email": "rs@x.co", "password": "Passw0rd!", "tenant_role": "admin"})
    token = db_client.post("/api/v1/auth/login", json={
        "username": "role-self-admin", "password": "Passw0rd!"}).json()["data"]["access_token"]
    me = {"Authorization": f"Bearer {token}"}
    uid = _row(db_session, "role-self-admin").id
    off = db_client.patch(f"{MEMBERS}/{uid}", headers=me, json={"is_active": False})
    assert off.status_code == 422 and off.json()["data"]["field"] == "is_active"
    down = db_client.patch(f"{MEMBERS}/{uid}", headers=me, json={"tenant_role": "viewer"})
    assert down.status_code == 422 and down.json()["data"]["field"] == "tenant_role"
    row = _row(db_session, "role-self-admin")
    assert row.is_active is True and row.tenant_role == "admin"


def test_platform_user_page_cannot_overwrite_or_move_owner(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="role-own")
    pa = make_platform_admin_headers(db_session)
    oid = _row(db_session, "owner-role-own").id
    resp = db_client.patch(f"/api/v1/admin/users/{oid}", headers=pa, json={"role": "viewer"})
    assert resp.status_code == 400, resp.text
    assert "负责人" in resp.json()["message"]
    other, tid2 = make_tenant_owner_headers(db_session, slug="role-own-2")
    moved = db_client.patch(f"/api/v1/admin/users/{oid}", headers=pa, json={"tenant_id": tid2})
    assert moved.status_code == 400
    row = _row(db_session, "owner-role-own")
    assert (row.tenant_role, row.tenant_id) == ("owner", tid)
