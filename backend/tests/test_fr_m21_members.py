"""T-14 / FR-M21：成员增改删；不能设超管；跨企业 404 同形；只读写拒绝。"""
from __future__ import annotations

from conftest import make_tenant_owner_headers
from platform_core.models.user import User
from sqlalchemy import select
import asyncio

MEMBERS = "/api/v1/members"
GHOST = "/api/v1/admin/tenants"
SORRY = "抱歉您没有权限"
FORBIDDEN = "FORBIDDEN"


def _member(db_session, tid: int, role: str, username: str) -> dict:
    from backend.services.auth_service import AuthService

    async def _go():
        async with db_session() as s:
            s.add(User(
                username=username, email=f"{username}@x.co", password_hash="x",
                role=role, tenant_id=tid, tenant_role=role, is_active=True,
            ))
            await s.commit()
            u = (await s.execute(select(User).where(User.username == username))).scalar_one()
            token = await AuthService(s).create_token({
                "id": u.id, "username": u.username, "is_admin": False, "role": role,
                "tenant_id": tid, "tenant_role": role, "is_platform_admin": False,
            })
            return token.access_token

    return {"Authorization": f"Bearer {asyncio.run(_go())}"}


def _ids(resp) -> list[int]:
    return [int(m["id"]) for m in resp.json()["data"]]


def test_gwt_m21_1_add_operator(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="m21-1")
    resp = db_client.post(
        MEMBERS, headers=owner,
        json={
            "username": "op-m21", "email": "op-m21@x.co",
            "password": "Passw0rd!", "tenant_role": "operator",
        },
    )
    assert resp.status_code in (200, 201), resp.text
    data = resp.json()["data"]
    assert data["username"] == "op-m21"
    assert data["tenant_role"] == "operator"
    assert data.get("is_platform_admin") is False
    listed = db_client.get(MEMBERS, headers=owner)
    assert "op-m21" in [m["username"] for m in listed.json()["data"]]


def test_gwt_m21_2_owner_sees_self(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="m21-2")
    listed = db_client.get(MEMBERS, headers=owner)
    assert listed.status_code == 200, listed.text
    names = [m["username"] for m in listed.json()["data"]]
    assert any(n.startswith("owner-") for n in names)


def test_gwt_m21_3_viewer_write_rejected_no_forbidden(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="m21-3")
    viewer = _member(db_session, tid, "viewer", "m21-3-ro")
    before = db_client.get(MEMBERS, headers=owner).json()["data"]
    added = db_client.post(
        MEMBERS, headers=viewer,
        json={"username": "x", "email": "x@x.co", "password": "Passw0rd!", "tenant_role": "viewer"},
    )
    assert added.status_code in (400, 403)
    body = added.json()
    assert FORBIDDEN not in str(body.get("message") or "")
    assert body.get("code") != FORBIDDEN
    after = db_client.get(MEMBERS, headers=owner).json()["data"]
    assert [m["username"] for m in after] == [m["username"] for m in before]


def test_gwt_m21_4_cannot_assign_platform_admin(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="m21-4")
    created = db_client.post(
        MEMBERS, headers=owner,
        json={
            "username": "m21-4-op", "email": "m21-4-op@x.co",
            "password": "Passw0rd!", "tenant_role": "operator",
        },
    )
    mid = created.json()["data"]["id"]
    patched = db_client.patch(
        f"{MEMBERS}/{mid}", headers=owner,
        json={"tenant_role": "platform_admin"},
    )
    assert patched.status_code in (400, 422), patched.text
    assert "超管" in patched.json()["message"] or "不合法" in patched.json()["message"]
    listed = db_client.get(MEMBERS, headers=owner).json()["data"]
    row = next(m for m in listed if m["id"] == mid)
    assert row["tenant_role"] == "operator"
    assert row.get("is_platform_admin") is False
    created2 = db_client.post(
        MEMBERS, headers=owner,
        json={
            "username": "m21-4-su", "email": "m21-4-su@x.co",
            "password": "Passw0rd!", "tenant_role": "superadmin",
            "is_platform_admin": True,
        },
    )
    assert created2.status_code in (400, 422)
    names = [m["username"] for m in db_client.get(MEMBERS, headers=owner).json()["data"]]
    assert "m21-4-su" not in names


def test_gwt_m21_5_cross_tenant_404_same_shape(db_client, db_session):
    a, tid_a = make_tenant_owner_headers(db_session, slug="m21-5a")
    b, tid_b = make_tenant_owner_headers(db_session, slug="m21-5b")
    created = db_client.post(
        MEMBERS, headers=b,
        json={
            "username": "b-op", "email": "b-op@x.co",
            "password": "Passw0rd!", "tenant_role": "operator",
        },
    )
    bid = created.json()["data"]["id"]
    ghost = db_client.get(GHOST, headers=a)
    patched = db_client.patch(
        f"{MEMBERS}/{bid}", headers=a, json={"tenant_role": "admin"},
    )
    assert patched.status_code == ghost.status_code == 404
    assert patched.json()["code"] == ghost.json()["code"] == "HTTP_404"
    assert patched.json()["message"] == ghost.json()["message"] == "Not Found"
    assert SORRY not in patched.text
    still = db_client.get(MEMBERS, headers=b).json()["data"]
    assert next(m for m in still if m["id"] == bid)["tenant_role"] == "operator"


def test_gwt_m21_6_empty_username(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="m21-6")
    before = len(db_client.get(MEMBERS, headers=owner).json()["data"])
    resp = db_client.post(
        MEMBERS, headers=owner,
        json={"username": "", "email": "empty@x.co", "password": "Passw0rd!", "tenant_role": "operator"},
    )
    assert resp.status_code in (400, 422)
    assert "填写" in resp.json()["message"] or "必填" in resp.json()["message"]
    assert len(db_client.get(MEMBERS, headers=owner).json()["data"]) == before


def test_gwt_m21_7_username_256(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="m21-7")
    before = len(db_client.get(MEMBERS, headers=owner).json()["data"])
    resp = db_client.post(
        MEMBERS, headers=owner,
        json={
            "username": "测" * 256, "email": "long@x.co",
            "password": "Passw0rd!", "tenant_role": "operator",
        },
    )
    assert resp.status_code in (400, 422)
    assert "长" in resp.json()["message"] or "最多" in resp.json()["message"]
    assert len(db_client.get(MEMBERS, headers=owner).json()["data"]) == before


def test_gwt_m21_remove_member(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="m21-rm")
    created = db_client.post(
        MEMBERS, headers=owner,
        json={
            "username": "gone", "email": "gone@x.co",
            "password": "Passw0rd!", "tenant_role": "viewer",
        },
    )
    mid = created.json()["data"]["id"]
    deleted = db_client.delete(f"{MEMBERS}/{mid}", headers=owner)
    assert deleted.status_code == 200
    assert mid not in _ids(db_client.get(MEMBERS, headers=owner))
