"""S2-1 子账号管理 API 验证（工单 37）

Seam（工单预确认）：/api/v1/members 端点（db_client + 真实 JWT 租户上下文）。
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import Delete, func, select, update as sa_update

from backend.services.auth_service import AuthService
from platform_core.exceptions import NotFoundException
from platform_core.models.notification import Notification
from platform_core.models.operation_log import OperationLog
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
        # 跨租户对照组（T4/F-01）：另一租户 owner，用于越权删除用例
        t2 = Tenant(slug=f"m2-{id(db_session)}", name="M2")
        s.add(t2)
        await s.flush()
        other = User(username="m-other", email="mx@x.local", password_hash="x",
                     role="admin", tenant_id=t2.id, tenant_role="owner")
        s.add(other)
        await s.commit()
        token2 = await svc.create_token({
            "id": other.id, "username": other.username, "is_admin": False,
            "role": "admin", "tenant_id": t2.id, "tenant_role": "owner",
            "is_platform_admin": False,
        })
        STATE["other"] = token2.access_token


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
    # created_at 契约：server_default 须经 refresh 回填（SQLite 隐式 RETURNING 掩盖
    # MySQL/aiomysql 的 MissingGreenlet，此断言固化回填口径防回归）
    assert data["created_at"], "create_member 必须返回非空 created_at"
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


def test_delete_member(db_client):
    mid = _ensure_member(db_client)
    resp = db_client.delete(f"/api/v1/members/{mid}", headers=_auth("owner"))
    assert resp.status_code == 200 and resp.json()["data"]["deleted"] is True
    listed = db_client.get("/api/v1/members", headers=_auth("owner")).json()["data"]
    assert mid not in [m["id"] for m in listed]


def test_cannot_delete_owner(db_client):
    listed = db_client.get("/api/v1/members", headers=_auth("owner")).json()["data"]
    owner_id = next(m["id"] for m in listed if m["tenant_role"] == "owner")
    resp = db_client.delete(f"/api/v1/members/{owner_id}", headers=_auth("owner"))
    assert resp.status_code == 422


def test_cannot_delete_self(db_client):
    """admin 角色成员可管理成员，但不可删除自己"""
    created = db_client.post(
        "/api/v1/members", headers=_auth("owner"),
        json={"username": "self-del", "email": "sd@x.local",
              "password": "Passw0rd!", "tenant_role": "admin"},
    )
    mid = created.json()["data"]["id"]
    login = db_client.post("/api/v1/auth/login",
                           json={"username": "self-del", "password": "Passw0rd!"})
    token = login.json()["data"]["access_token"]
    resp = db_client.delete(f"/api/v1/members/{mid}",
                            headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422


# ---------------- T4：删除语义收口（F-01/F-02/F-03/F-05） ----------------


def test_delete_member_not_found(db_client):
    """F-01：不存在 id → 404"""
    resp = db_client.delete("/api/v1/members/999999", headers=_auth("owner"))
    assert resp.status_code == 404


def test_viewer_cannot_delete_member(db_client):
    """F-01：无权限角色 DELETE → 403，数据未动"""
    mid = _ensure_member(db_client)
    resp = db_client.delete(f"/api/v1/members/{mid}", headers=_auth("viewer"))
    assert resp.status_code == 403
    listed = db_client.get("/api/v1/members", headers=_auth("owner")).json()["data"]
    assert mid in [m["id"] for m in listed]


def test_delete_member_cross_tenant_404_and_untouched(db_client, db_session):
    """F-01：跨租户删除 → 404（MemberService 显式 tenant_id 条件），目标行未动"""
    mid = _ensure_member(db_client)

    async def _deleted_at():
        async with db_session() as s:
            return (await s.execute(
                select(User.deleted_at).where(User.id == mid))).scalar_one()

    assert asyncio.run(_deleted_at()) is None  # 前置：未删
    resp = db_client.delete(f"/api/v1/members/{mid}", headers=_auth("other"))
    assert resp.status_code == 404
    listed = db_client.get("/api/v1/members", headers=_auth("owner")).json()["data"]
    assert mid in [m["id"] for m in listed]  # 本租户视角仍在
    assert asyncio.run(_deleted_at()) is None  # 库级断言：行未被软删


def test_delete_member_is_soft_delete_and_blocks_login(db_client, db_session):
    """F-02 口径：删除=软删（行保留+停用）——审计归因不丢的前提；登录即时失效"""
    created = db_client.post(
        "/api/v1/members", headers=_auth("owner"),
        json={"username": "soft-del", "email": "sdl@x.local",
              "password": "Passw0rd!", "tenant_role": "viewer"},
    )
    mid = created.json()["data"]["id"]
    resp = db_client.delete(f"/api/v1/members/{mid}", headers=_auth("owner"))
    assert resp.status_code == 200 and resp.json()["data"]["deleted"] is True

    async def _row():
        async with db_session() as s:
            return (await s.execute(
                select(User.deleted_at, User.is_active).where(User.id == mid))).one()

    deleted_at, is_active = asyncio.run(_row())
    assert deleted_at is not None  # 软删（非物理删）：users 行保留
    assert is_active is False  # 登录即时失效
    listed = db_client.get("/api/v1/members", headers=_auth("owner")).json()["data"]
    assert mid not in [m["id"] for m in listed]  # 列表不可见
    login = db_client.post("/api/v1/auth/login",
                           json={"username": "soft-del", "password": "Passw0rd!"})
    assert login.status_code == 401


def test_delete_member_audit_preserved(db_client, db_session):
    """F-02 回归固化：被删成员的历史审计仍在租户视图（软删保行 → JOIN 归因不丢）"""
    created = db_client.post(
        "/api/v1/members", headers=_auth("owner"),
        json={"username": "gone-admin", "email": "ga@x.local",
              "password": "Passw0rd!", "tenant_role": "admin"},
    )
    mid = created.json()["data"]["id"]

    async def _seed_log():  # 该成员生前的审计留痕（record_audit 走独立引擎，测试态直插）
        async with db_session() as s:
            s.add(OperationLog(actor_id=mid, actor_name="gone-admin",
                               action="member.create", target="user#42"))
            await s.commit()

    asyncio.run(_seed_log())
    resp = db_client.delete(f"/api/v1/members/{mid}", headers=_auth("owner"))
    assert resp.status_code == 200
    audit = db_client.get("/api/v1/members/audit", headers=_auth("owner")).json()["data"]
    rows = [r for r in audit if r["actor_name"] == "gone-admin"]
    assert rows, "被删成员的历史审计必须保留在租户审计视图"
    assert rows[0]["action"] == "member.create"


def test_delete_member_twice_second_is_404_not_500(db_client):
    """F-03：重复删除（重试/双击）——第二次 404，绝不 500"""
    mid = _ensure_member(db_client)
    first = db_client.delete(f"/api/v1/members/{mid}", headers=_auth("owner"))
    assert first.status_code == 200
    second = db_client.delete(f"/api/v1/members/{mid}", headers=_auth("owner"))
    assert second.status_code == 404


def test_delete_member_concurrent_race_graceful(db_session):
    """F-03 竞态窗口：service select 到活行后、update 落库前被并发请求抢先软删
    ——乐观条件 rowcount==0 → NotFoundException（404 语义），无 StaleDataError 逃逸 500
    """
    from backend.services.member_service import MemberService

    async def _run():
        async with db_session() as seed_s:
            t = Tenant(slug=f"race-{id(db_session)}", name="R")
            seed_s.add(t)
            await seed_s.flush()
            victim = User(username="race-victim", email="rv@x.local", password_hash="x",
                          role="viewer", tenant_id=t.id, tenant_role="viewer")
            seed_s.add(victim)
            await seed_s.commit()
            tid, uid = t.id, victim.id

        async with db_session() as a, db_session() as b:
            raced = {"done": False}

            class RaceSession:
                """包装 A 会话：首个 DML（notifications 清理）落库前，
                先释放 A 的事务，再让并发请求 B 抢先软删提交——精确复现
                select（活行）→ update（行已没了）的竞态窗口"""

                def __init__(self, inner):
                    self._inner = inner

                async def execute(self, stmt, *args, **kw):
                    if isinstance(stmt, Delete) and not raced["done"]:
                        raced["done"] = True
                        await self._inner.rollback()  # 释放读事务，放行 B 的写
                        await b.execute(
                            sa_update(User).where(User.id == uid)
                            .values(deleted_at=func.now(), is_active=False))
                        await b.commit()
                    return await self._inner.execute(stmt, *args, **kw)

            svc = MemberService(RaceSession(a))
            raised = None
            try:
                await svc.delete_member(tid, uid, actor_id=-1)
            except NotFoundException:
                raised = True
            assert raised is True, "并发抢先删除须抛 NotFoundException（404），而非异常逃逸 500"

    asyncio.run(_run())


def test_delete_member_clears_inbox_and_records_audit(db_client, db_session):
    """F-05：删除时收件箱物理清理 + member.delete 审计写入"""
    created = db_client.post(
        "/api/v1/members", headers=_auth("owner"),
        json={"username": "inbox-user", "email": "iu@x.local",
              "password": "Passw0rd!", "tenant_role": "viewer"},
    )
    mid = created.json()["data"]["id"]
    tid = STATE["tenant"]

    async def _seed_inbox():
        async with db_session() as s:
            s.add_all([
                Notification(tenant_id=tid, user_id=mid, type="system",
                             title="t1", content="c"),
                Notification(tenant_id=tid, user_id=mid, type="alert",
                             title="t2", content="c"),
            ])
            await s.commit()

    asyncio.run(_seed_inbox())
    with patch("backend.app.api.v1.members.record_audit", new_callable=AsyncMock) as audit:
        resp = db_client.delete(f"/api/v1/members/{mid}", headers=_auth("owner"))
    assert resp.status_code == 200
    audit.assert_awaited_once()
    assert audit.await_args.args[2] == "member.delete"  # (session, user, action, target)
    assert audit.await_args.args[3] == f"user#{mid}"

    async def _count_inbox():
        async with db_session() as s:
            return (await s.execute(
                select(func.count()).select_from(Notification)
                .where(Notification.user_id == mid))).scalar_one()

    assert asyncio.run(_count_inbox()) == 0  # 收件箱已随账号清理


def test_deleted_member_not_operable_or_reusable(db_client):
    """软删行善后：后续操作 404；username 被唯一约束占用 → 同名重建 422（非 500）"""
    created = db_client.post(
        "/api/v1/members", headers=_auth("owner"),
        json={"username": "dup-name", "email": "dup@x.local",
              "password": "Passw0rd!", "tenant_role": "viewer"},
    )
    mid = created.json()["data"]["id"]
    assert db_client.delete(f"/api/v1/members/{mid}", headers=_auth("owner")).status_code == 200

    assert db_client.patch(f"/api/v1/members/{mid}", headers=_auth("owner"),
                           json={"is_active": True}).status_code == 404
    assert db_client.post(f"/api/v1/members/{mid}/reset-password",
                          headers=_auth("owner"),
                          json={"new_password": "NewPass1!"}).status_code == 404

    again = db_client.post(
        "/api/v1/members", headers=_auth("owner"),
        json={"username": "dup-name", "email": "dup2@x.local",
              "password": "Passw0rd!", "tenant_role": "viewer"},
    )
    assert again.status_code == 422  # 优雅报错，而非 IntegrityError 500
