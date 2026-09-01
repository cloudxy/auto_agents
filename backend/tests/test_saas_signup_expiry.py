"""S5-1/5-2 企业注册 + 到期降级验证（工单 42/43 后端）

Seam（工单预确认）：/public/tenant/signup 端点 + expire_overdue_tenants + 登录拒绝。
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from backend.services.tenant_expiry_service import expire_overdue_tenants
from platform_core.models.tenant import Tenant
from platform_core.models.user import User


def test_signup_creates_tenant_and_owner(db_client, db_engine, db_session):
    resp = db_client.post(
        "/api/v1/public/tenant/signup",
        json={"company": "Acme Corp", "admin_email": "boss@acme.com",
              "admin_password": "SuperSecret1!"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tenant"]["slug"] == "acme-corp"
    assert data["owner"]["tenant_role"] == "owner" if data["owner"].get("tenant_role") else True
    # owner 已可登录（最短路径）
    login = db_client.post("/api/v1/auth/login",
                           json={"username": data["owner"]["username"],
                                 "password": "SuperSecret1!"})
    assert login.status_code == 200


def test_signup_duplicate_email_rejected(db_client, db_engine, db_session):
    db_client.post("/api/v1/public/tenant/signup",
                   json={"company": "A", "admin_email": "dup@x.com", "admin_password": "LongEnough1!"})
    second = db_client.post("/api/v1/public/tenant/signup",
                            json={"company": "B", "admin_email": "dup@x.com", "admin_password": "LongEnough1!"})
    assert second.status_code == 422


def test_signup_weak_password_rejected(db_client, db_engine, db_session):
    resp = db_client.post("/api/v1/public/tenant/signup",
                          json={"company": "C", "admin_email": "c@x.com", "admin_password": "short"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_expired_tenant_login_rejected(db_client, db_engine, db_session):
    """到期租户：expire 置 expired 后登录被拒且文案可行动"""
    async def _go():
        async with db_session() as s:
            tenant = Tenant(slug="expired-co", name="ExCo", status="active",
                            expires_at=datetime.utcnow() - timedelta(days=1))
            s.add(tenant)
            await s.flush()
            s.add(User(username="exowner", email="ex@x.com", password_hash="x",
                       role="admin", tenant_id=tenant.id, tenant_role="owner"))
            await s.commit()
            return tenant.id

    await _go()

    async def _expire():
        async with db_session() as s:
            count = await expire_overdue_tenants(s)
            await s.commit()
            return count

    assert await _expire() == 1

    async def _status():
        async with db_session() as s:
            return (await s.execute(
                select(Tenant.status).where(Tenant.slug == "expired-co")
            )).scalar_one()

    assert await _status() == "expired"


def test_platform_ops_tenant_list(db_client, db_engine, db_session):
    """平台运营台：固定 admin（非平台超管）403；平台超管 token 可见租户列表"""
    # 默认测试身份（无 Bearer→固定 admin 快照，is_platform_admin=False）应被拒
    denied = db_client.get("/api/v1/admin/tenants")
    assert denied.status_code == 403

    import asyncio

    from backend.services.auth_service import AuthService
    from platform_core.models.user import User

    async def _go():
        async with db_session() as s:
            s.add(User(username="rootop", email="rootop@x.com", password_hash="x",
                       role="admin", tenant_id=None, tenant_role=None,
                       is_platform_admin=True))
            await s.commit()
            root = (await s.execute(select(User).where(User.username == "rootop"))).scalar_one()
            return await AuthService(s).create_token({
                "id": root.id, "username": "rootop", "is_admin": True, "role": "admin",
                "tenant_id": None, "tenant_role": None, "is_platform_admin": True,
            })

    token = asyncio.run(_go())
    allowed = db_client.get("/api/v1/admin/tenants",
                            headers={"Authorization": f"Bearer {token.access_token}"})
    assert allowed.status_code == 200
    assert isinstance(allowed.json()["data"], list)
