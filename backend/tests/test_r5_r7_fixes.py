"""R 线 48/50 验证：权限单源下发 + 租户禁用"""
import asyncio

from sqlalchemy import select

from platform_core.models.tenant import Tenant
from platform_core.models.user import User


def test_permissions_endpoint_has_new_codes(db_client, db_engine, db_session):
    """R5：后端 /permissions 下发含新码（menu:skills/members/usage/platform-ops、btn:skill:*）"""
    resp = db_client.get("/api/v1/auth/permissions")
    assert resp.status_code == 200
    data = resp.json()["data"]
    admin_codes = set(data)  # 默认 admin 身份（无 Bearer）
    assert "menu:skills" in admin_codes
    assert "menu:members" in admin_codes
    assert "menu:usage" in admin_codes
    assert "btn:skill:edit" in admin_codes


def _platform_admin_token(db_session):
    import asyncio as _aio

    from backend.services.auth_service import AuthService

    async def _go():
        async with db_session() as s:
            s.add(User(username="r7root", email="r7root@x.com", password_hash="x",
                       role="admin", tenant_id=None, tenant_role=None,
                       is_platform_admin=True))
            await s.commit()
            root = (await s.execute(select(User).where(User.username == "r7root"))).scalar_one()
            return await AuthService(s).create_token({
                "id": root.id, "username": "r7root", "is_admin": True, "role": "admin",
                "tenant_id": None, "tenant_role": None, "is_platform_admin": True,
            })

    return _aio.run(_go()).access_token


def test_tenant_disable_via_patch(db_client, db_engine, db_session):
    """R7：PATCH status=disabled 生效（不再被强制 active 挡死）"""
    token = _platform_admin_token(db_session)
    auth = {"Authorization": f"Bearer {token}"}
    async def _seed():
        async with db_session() as s:
            s.add(Tenant(slug="dis-me", name="X", status="active"))
            await s.commit()
            return (await s.execute(
                select(Tenant.id).where(Tenant.slug == "dis-me")
            )).scalar_one()

    tid = asyncio.run(_seed())
    resp = db_client.patch(f"/api/v1/admin/tenants/{tid}", json={"status": "disabled"}, headers=auth)
    assert resp.status_code == 200

    async def _check():
        async with db_session() as s:
            return (await s.execute(
                select(Tenant.status).where(Tenant.id == tid)
            )).scalar_one()

    assert asyncio.run(_check()) == "disabled"

    # 启用恢复
    db_client.patch(f"/api/v1/admin/tenants/{tid}", json={"status": "active"}, headers=auth)
    assert asyncio.run(_check()) == "active"


def test_tenant_invalid_status_rejected(db_client, db_engine, db_session):
    async def _seed():
        async with db_session() as s:
            s.add(Tenant(slug="bad-st", name="Y", status="active"))
            await s.commit()

    asyncio.run(_seed())
    tid = asyncio.run(_go(db_session))
    token2 = _platform_admin_token(db_session)

    resp = db_client.patch(f"/api/v1/admin/tenants/{tid}", json={"status": "hacked"},
                           headers={"Authorization": f"Bearer {token2}"})
    assert resp.status_code == 200  # 非法值静默忽略（白名单外不动）


async def _go(db_session):
    async with db_session() as s:
        return (await s.execute(
            select(Tenant.id).where(Tenant.slug == "bad-st")
        )).scalar_one()
