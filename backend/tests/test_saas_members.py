"""S2-1 子账号管理 API 验证（工单 37）

Seam（工单预确认）：/api/v1/members 端点（db_client + 真实 JWT 租户上下文）。
"""
import asyncio

import pytest

from backend.services.auth_service import AuthService
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

STATE: dict = {}


async def _seed(db_session) -> None:
    async with db_session() as s:
        t = Tenant(slug=f"m-{id(db_session)}", name="M")
        s.add(t)
        await s.flush()
        owner = User(username="m-owner", email="mo@x.local", password_hash="x",
                     role="admin", tenant_id=t.id, tenant_role="owner")
        viewer = User(username="m-viewer", email="mv@x.local", password_hash="x",
                      role="viewer", tenant_id=t.id, tenant_role="viewer")
        s.add_all([owner, viewer])
        await s.commit()
        svc = AuthService(s)
        for label, user, role in (("owner", owner, "owner"), ("viewer", viewer, "viewer")):
            token = await svc.create_token({
                "id": user.id, "username": user.username, "is_admin": False,
                "role": "admin" if role == "owner" else "viewer",
                "tenant_id": t.id, "tenant_role": role, "is_platform_admin": False,
            })
            STATE[label] = token.access_token
        STATE["tenant"] = t.id


@pytest.fixture(autouse=True)
def seeded(db_session):
    asyncio.run(_seed(db_session))
    yield


def _auth(label: str) -> dict:
    return {"Authorization": f"Bearer {STATE[label]}"}


def test_create_member(db_client):
    resp = db_client.post(
        "/api/v1/members",
        headers=_auth("owner"),
        json={"username": "new-member", "email": "nm@x.local",
              "password": "Passw0rd!", "tenant_role": "operator"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["username"] == "new-member" and data["tenant_role"] == "operator"
    STATE["new_id"] = data["id"]


def test_list_members_scoped_to_tenant(db_client):
    resp = db_client.get("/api/v1/members", headers=_auth("owner"))
    assert resp.status_code == 200
    usernames = [m["username"] for m in resp.json()["data"]]
    assert "m-owner" in usernames


def test_viewer_cannot_manage(db_client):
    resp = db_client.post(
        "/api/v1/members", headers=_auth("viewer"),
        json={"username": "x", "email": "x@x.local", "password": "Passw0rd!", "tenant_role": "viewer"},
    )
    assert resp.status_code == 403


def _ensure_member(db_client) -> int:
    """每用例独立库：现建一个成员返回其 id（username 冲突时换名）"""
    import itertools

    for i in itertools.count():
        username = f"mb{i}"
        resp = db_client.post(
            "/api/v1/members", headers=_auth("owner"),
            json={"username": username, "email": f"mb{i}@x.local",
                  "password": "Passw0rd!", "tenant_role": "viewer"},
        )
        if resp.status_code == 200:
            return resp.json()["data"]["id"]


def test_change_role_and_disable(db_client):
    mid = _ensure_member(db_client)
    patch = db_client.patch(f"/api/v1/members/{mid}", headers=_auth("owner"),
                            json={"tenant_role": "admin"})
    assert patch.status_code == 200 and patch.json()["data"]["tenant_role"] == "admin"

    disable = db_client.patch(f"/api/v1/members/{mid}", headers=_auth("owner"),
                              json={"is_active": False})
    assert disable.status_code == 200


def test_reset_password(db_client):
    mid = _ensure_member(db_client)
    resp = db_client.post(f"/api/v1/members/{mid}/reset-password",
                          headers=_auth("owner"), json={"new_password": "NewPass1!"})
    assert resp.status_code == 200
