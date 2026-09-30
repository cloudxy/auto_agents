"""会话吊销（审计 BUG-46 / QA-B1-12 回归）

- 用户被迁到别的企业后，旧令牌不能再以原企业作用域访问
- 重置密码后已签发的令牌立即失效（token_version，迁移 054）；停用即时 401；降级每请求按库重算
- BUG-46 核验结论：迁租户后旧令牌在租户作用域内查不到该用户 → 已是 401（审查怀疑不成立，本文件留作回归）
"""
from __future__ import annotations

import asyncio

from sqlalchemy import update

from conftest import make_tenant_owner_headers
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

ME = "/api/v1/members"


def _member_token(db_session, tid: int, username: str, role: str = "admin"):
    from backend.services.auth_service import AuthService
    from sqlalchemy import select

    async def _go():
        async with db_session() as s:
            s.add(User(username=username, email=f"{username}@x.co", password_hash="x",
                       role=role, tenant_id=tid, tenant_role=role, is_active=True))
            await s.commit()
            u = (await s.execute(select(User).where(User.username == username))).scalar_one()
            tok = await AuthService(s).create_token({
                "id": u.id, "username": u.username, "is_admin": role == "admin", "role": role,
                "tenant_id": tid, "tenant_role": role, "is_platform_admin": False,
            })
            return {"Authorization": f"Bearer {tok.access_token}"}, int(u.id)

    return asyncio.run(_go())


def test_moved_user_old_token_rejected(db_client, db_session):
    _owner, tid_a = make_tenant_owner_headers(db_session, slug="tv-a")
    headers, uid = _member_token(db_session, tid_a, "tv-mover")
    assert db_client.get(ME, headers=headers).status_code == 200

    async def _move():
        async with db_session() as s:
            b = Tenant(slug="tv-b", name="乙")
            s.add(b)
            await s.flush()
            await s.execute(update(User).where(User.id == uid).values(tenant_id=b.id))
            await s.commit()

    asyncio.run(_move())
    assert db_client.get(ME, headers=headers).status_code == 401


def test_password_reset_revokes_existing_token(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="tv-reset")
    headers, uid = _member_token(db_session, tid, "tv-victim", role="operator")
    assert db_client.get("/api/v1/auth/permissions", headers=headers).status_code == 200
    resp = db_client.post(f"{ME}/{uid}/reset-password", headers=owner, json={"new_password": "NewPass1!"})
    assert resp.status_code == 200, resp.text
    assert db_client.get("/api/v1/auth/permissions", headers=headers).status_code == 401


def test_disable_revokes_existing_token(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="tv-disable")
    headers, uid = _member_token(db_session, tid, "tv-off", role="operator")
    assert db_client.patch(f"{ME}/{uid}", headers=owner, json={"is_active": False}).status_code == 200
    assert db_client.get("/api/v1/auth/permissions", headers=headers).status_code == 401


def test_downgrade_takes_effect_on_existing_token(db_client, db_session):
    """降级无需吊销：权限每请求按库重算，旧令牌立刻失去成员管理权"""
    owner, tid = make_tenant_owner_headers(db_session, slug="tv-down")
    headers, uid = _member_token(db_session, tid, "tv-down-admin", role="admin")
    assert db_client.get(ME, headers=headers).status_code == 200
    assert db_client.patch(f"{ME}/{uid}", headers=owner, json={"tenant_role": "viewer"}).status_code == 200
    resp = db_client.get(ME, headers=headers)
    assert resp.status_code != 200
    assert resp.json()["code"] == "MEMBER_ROLE_NOT_ALLOWED"


def test_new_login_after_reset_works(db_client, db_session):
    """重置后用新密码登录拿到的新令牌可用（tv 随登录签发）"""
    owner, tid = make_tenant_owner_headers(db_session, slug="tv-relogin")
    _headers, uid = _member_token(db_session, tid, "tv-relogin-user", role="operator")
    assert db_client.post(f"{ME}/{uid}/reset-password", headers=owner,
                          json={"new_password": "NewPass1!"}).status_code == 200
    login = db_client.post("/api/v1/auth/login", json={"username": "tv-relogin-user", "password": "NewPass1!"})
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    assert db_client.get("/api/v1/auth/permissions",
                         headers={"Authorization": f"Bearer {token}"}).status_code == 200
