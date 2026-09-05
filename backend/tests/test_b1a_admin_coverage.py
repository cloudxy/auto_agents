"""B1a 零覆盖路由清剿（管理域）：/admin/tenants 与 /admin/users 的鉴权缺口

覆盖路由清单（本轮补缺口；正常路径已由既有文件覆盖，见映射）：
- GET  /api/v1/admin/tenants           匿名 401
  （403 普通admin / 200 平台超管 → test_saas_signup_expiry.py::test_platform_ops_tenant_list）
- POST /api/v1/admin/tenants           匿名 401 / viewer 403 / slug 撞名容错 + 落库副作用
  （B5 修复 F-1：守卫对齐兄弟路由为 require_platform_admin，正面路径需平台超管
  Bearer 真链路；普通 admin 现为 403）
- PATCH /api/v1/admin/tenants/{id}     匿名 401 / 非平台 admin 403 / 不存在 404
  （status 白名单 → test_r5_r7_fixes.py）
- GET|POST|PATCH|DELETE /api/v1/admin/users   匿名 401 / viewer 403
  （CRUD 正常路径 + 防自锁护栏 → test_admin_users_crud.py）

权限断言口径：401 = 匿名无凭据；403 = 低权限角色直调（绕过前端隐藏入口）。
匿名用例只声明 client（特权 fixture 会改写共享 TestClient 的鉴权 override）；
平台超管正面路径经 _platform_bearer 真链路（JWT→DB 快照，conftest override
对带 Bearer 请求走生产链路）。
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from platform_core.models.tenant import Tenant
from platform_core.models.user import User

TENANTS_URL = "/api/v1/admin/tenants"
USERS_URL = "/api/v1/admin/users"

_VALID_USER_BODY = {
    "username": "b1a-probe", "email": "probe@b1a.co",
    "password": "LongEnough1!", "role": "viewer",
}


def _platform_bearer(db_session) -> dict:
    """平台超管 Bearer 头（真链路：建 platform 租户 + is_platform_admin 用户 + JWT，
    同 test_patch_tenant_not_found_404 的既有模式）。B5 后 POST /admin/tenants
    正面路径需此身份（require_platform_admin）。"""
    from backend.services.auth_service import AuthService

    async def _go():
        async with db_session() as s:
            platform = Tenant(slug="platform", name="平台租户")
            s.add(platform)
            await s.flush()
            s.add(User(username="b1a-root", email="b1a-root@x.com", password_hash="x",
                       role="admin", tenant_id=platform.id, tenant_role=None,
                       is_platform_admin=True))
            await s.commit()
            root = (await s.execute(
                select(User).where(User.username == "b1a-root"))).scalar_one()
            token = await AuthService(s).create_token({
                "id": root.id, "username": "b1a-root", "is_admin": True, "role": "admin",
                "tenant_id": None, "tenant_role": None, "is_platform_admin": True,
            })
            return token.access_token

    return {"Authorization": f"Bearer {asyncio.run(_go())}"}


# ---------------------------------------------------------------------------
# POST /api/v1/admin/tenants：slug 撞名容错 + 副作用
# ---------------------------------------------------------------------------


def test_create_tenant_slug_dedup_persists(db_client, db_session):
    """平台超管同名公司两次创建：均 201（撞名不阻断，slug 追缀区分）；库内恰两行 active"""
    auth = _platform_bearer(db_session)
    first = db_client.post(TENANTS_URL, json={"name": "撞名公司"}, headers=auth)
    second = db_client.post(TENANTS_URL, json={"name": "撞名公司"}, headers=auth)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    slug1, slug2 = first.json()["data"]["slug"], second.json()["data"]["slug"]
    assert slug1 != slug2  # 容错追缀：slug 互异

    async def _check():
        async with db_session() as s:
            return list((await s.execute(select(Tenant))).scalars().all())

    rows = asyncio.run(_check())
    # 副作用断言：撞名两行 + helper 的 platform 租户（slug=platform）恰三行
    assert {r.slug for r in rows} == {slug1, slug2, "platform"}
    assert all(r.status == "active" for r in rows)  # 新建默认 active


def test_create_tenant_explicit_slug_persists(db_client, db_session):
    """平台超管显式 slug：按入参落库（slug 是租户登录域键，回执与库内一致）"""
    resp = db_client.post(TENANTS_URL, json={"name": "指定公司", "slug": "b1a-custom"},
                          headers=_platform_bearer(db_session))
    assert resp.status_code == 201
    assert resp.json()["data"]["slug"] == "b1a-custom"

    async def _check():
        async with db_session() as s:
            return (await s.execute(
                select(Tenant).where(Tenant.slug == "b1a-custom"))).scalar_one()

    assert asyncio.run(_check()).name == "指定公司"


def test_create_tenant_anonymous_401(client, db_session):
    """匿名创建公司 → 401，零落库"""
    resp = client.post(TENANTS_URL, json={"name": "幽灵公司"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_FAILED"

    async def _check():
        async with db_session() as s:
            return len(list((await s.execute(select(Tenant))).scalars().all()))

    assert asyncio.run(_check()) == 0


def test_create_tenant_viewer_403(viewer_client, db_session):
    """viewer 直调创建公司 → 403，零落库"""
    resp = viewer_client.post(TENANTS_URL, json={"name": "越权公司"})
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"

    async def _check():
        async with db_session() as s:
            return len(list((await s.execute(select(Tenant))).scalars().all()))

    assert asyncio.run(_check()) == 0


def test_create_tenant_plain_admin_403(db_client, admin_client, db_session):
    """B5 修复 F-1（用例由锁定 201 翻转为 403）：普通 admin（非平台超管）
    创建租户 → 403——POST 守卫已对齐兄弟路由 GET/PATCH 的 require_platform_admin"""
    resp = admin_client.post(TENANTS_URL, json={"name": "普通管理员建"})
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "FORBIDDEN"

    async def _check():
        async with db_session() as s:
            return len(list((await s.execute(select(Tenant))).scalars().all()))

    assert asyncio.run(_check()) == 0  # 越权路径零落库


# ---------------------------------------------------------------------------
# GET /api/v1/admin/tenants：匿名 401（其余分支见 signup_expiry 文件）
# ---------------------------------------------------------------------------


def test_list_tenants_anonymous_401(client):
    resp = client.get(TENANTS_URL)
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_FAILED"


# ---------------------------------------------------------------------------
# PATCH /api/v1/admin/tenants/{id}：401 / 403 / 404
# ---------------------------------------------------------------------------


def test_patch_tenant_anonymous_401(client):
    resp = client.patch(f"{TENANTS_URL}/1", json={"status": "disabled"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_FAILED"


def test_patch_tenant_plain_admin_403(admin_client):
    """非平台超管的 admin → 403（require_platform_admin 守卫）"""
    resp = admin_client.patch(f"{TENANTS_URL}/1", json={"status": "disabled"})
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_patch_tenant_not_found_404(db_client, db_engine, db_session):
    """平台超管真链路（Bearer）：改不存在租户 → 404 NOT_FOUND"""
    from backend.services.auth_service import AuthService

    async def _go():
        async with db_session() as s:
            platform = Tenant(slug="platform", name="平台租户")
            s.add(platform)
            await s.flush()
            s.add(User(username="b1a-root", email="b1a-root@x.com", password_hash="x",
                       role="admin", tenant_id=platform.id, tenant_role=None,
                       is_platform_admin=True))
            await s.commit()
            root = (await s.execute(
                select(User).where(User.username == "b1a-root"))).scalar_one()
            token = await AuthService(s).create_token({
                "id": root.id, "username": "b1a-root", "is_admin": True, "role": "admin",
                "tenant_id": None, "tenant_role": None, "is_platform_admin": True,
            })
            return token.access_token

    token = asyncio.run(_go())
    resp = db_client.patch(f"{TENANTS_URL}/99999999", json={"status": "disabled"},
                           headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# /admin/users 四操作：匿名 401 / viewer 403（正常路径见 test_admin_users_crud.py）
# ---------------------------------------------------------------------------


def test_admin_users_anonymous_401(client):
    """匿名直调用户管理四操作 → 401（请求体合法，确保先过校验再撞守卫）"""
    assert client.get(USERS_URL).status_code == 401
    assert client.post(USERS_URL, json=_VALID_USER_BODY).status_code == 401
    assert client.patch(f"{USERS_URL}/1", json={"role": "viewer"}).status_code == 401
    assert client.delete(f"{USERS_URL}/1").status_code == 401


def test_admin_users_viewer_403(viewer_client, db_session):
    """viewer 直调四操作 → 403，且零写入"""
    assert viewer_client.get(USERS_URL).status_code == 403
    assert viewer_client.post(USERS_URL, json=_VALID_USER_BODY).status_code == 403
    assert viewer_client.patch(f"{USERS_URL}/1", json={"role": "viewer"}).status_code == 403
    assert viewer_client.delete(f"{USERS_URL}/1").status_code == 403

    async def _check():
        async with db_session() as s:
            return len(list((await s.execute(select(User))).scalars().all()))

    assert asyncio.run(_check()) == 0  # 越权路径零副作用
