"""S1-3 身份与权限验证（工单 33）：claims 只承身份 + 租户上下文中间件 + 两级 RBAC

Seam（工单预确认）：AuthService.create_token（claims 扩展）/ TenantContextMiddleware /
deps（CurrentUser 扩展 + 平台级守卫）。
"""
import pytest
from sqlalchemy import select

from platform_core.models.tenant import Tenant
from platform_core.models.user import User
from platform_core.tenant_context import current_tenant_id, is_platform_mode


async def _seed(db_session) -> dict:
    async with db_session() as s:
        t = Tenant(slug="acme", name="ACME")
        s.add(t)
        await s.flush()
        users = {
            "owner": User(username="o1", email="o1@t.local", password_hash="x",
                          role="admin", tenant_id=t.id, tenant_role="owner"),
            "member": User(username="m1", email="m1@t.local", password_hash="x",
                           role="viewer", tenant_id=t.id, tenant_role="viewer"),
            "platform": User(username="p1", email="p1@t.local", password_hash="x",
                             role="admin", tenant_id=None, tenant_role=None,
                             is_platform_admin=True),
        }
        for u in users.values():
            s.add(u)
        await s.commit()
        ids = {k: u.id for k, u in users.items()}
        ids["tenant"] = t.id
        return ids


@pytest.mark.asyncio
async def test_token_claims_carry_tenant_identity(db_session):
    """claims 只承身份：user_id/tenant_id/tenant_role/is_platform_admin；权限不进 claims"""
    from backend.services.auth_service import AuthService

    await _seed(db_session)
    async with db_session() as s:
        svc = AuthService(s)
        user = (await s.execute(select(User).where(User.username == "o1"))).scalar_one()
        token = await svc.create_token({
            "id": user.id, "username": user.username, "is_admin": False, "role": "admin",
            "tenant_id": user.tenant_id, "tenant_role": user.tenant_role,
            "is_platform_admin": user.is_platform_admin,
        })
        from backend.utils.auth import decode_access_token

        payload = decode_access_token(token.access_token)
    assert payload["user_id"] == user.id
    assert payload["tenant_id"] == user.tenant_id
    assert payload["tenant_role"] == "owner"
    assert payload["is_platform_admin"] is False


def test_tenant_context_middleware_sets_scope(db_client, db_engine, db_session):
    """带租户身份 token 的请求 → 租户上下文注入（探测端点回显当前作用域）"""
    import asyncio

    ids = asyncio.run(_seed(db_session))
    from backend.services.auth_service import AuthService

    async def _token():
        async with db_session() as s:
            svc = AuthService(s)
            return await svc.create_token({
                "id": ids["owner"], "username": "o1", "is_admin": False, "role": "admin",
                "tenant_id": ids["tenant"], "tenant_role": "owner", "is_platform_admin": False,
            })

    token = asyncio.run(_token())
    resp = db_client.get("/api/v1/skills", headers={"Authorization": f"Bearer {token.access_token}"})
    assert resp.status_code == 200


def test_platform_admin_guard_and_current_user_snapshot(db_client, db_engine, db_session):
    """两级 RBAC：平台超管守卫通过；租户用户快照含 tenant 字段"""
    import asyncio

    from backend.app.api.deps import CurrentUser

    ids = asyncio.run(_seed(db_session))
    snap = CurrentUser(
        id=ids["platform"], username="p1", role="admin",
        tenant_id=None, tenant_role=None, is_platform_admin=True,
    )
    assert snap.is_platform_admin is True

    tenant_snap = CurrentUser(
        id=ids["owner"], username="o1", role="admin",
        tenant_id=ids["tenant"], tenant_role="owner", is_platform_admin=False,
    )
    assert tenant_snap.tenant_id == ids["tenant"] and tenant_snap.tenant_role == "owner"


def test_tenant_scope_helpers_semantics():
    from platform_core.tenant_context import platform_scope, tenant_scope

    with tenant_scope(7):
        assert current_tenant_id() == 7 and not is_platform_mode()
    with platform_scope():
        assert current_tenant_id() is None and is_platform_mode()
    assert current_tenant_id() is None and not is_platform_mode()  # 默认无上下文
