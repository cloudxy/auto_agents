"""T-26 平台基座保护：种子 admin 不可删 + 平台租户三名守卫（FR-94 / GWT-94.1…94.5）

Seam：delete_user 单点（user_service）+ tenant 写服务单点（tenant_admin_service）；
越权 404 同形走既有 require_platform_admin_or_404（守卫核对）。
"""
import asyncio

import pytest
from sqlalchemy import select

from conftest import make_platform_admin_headers, make_tenant_owner_headers

USERS_URL = "/api/v1/admin/users"
TENANTS_URL = "/api/v1/admin/tenants"


async def _add_user(db_session, *, username: str, email: str, tenant_id: int,
                    is_platform_admin: bool = False) -> int:
    from platform_core.models.user import User

    async with db_session() as s:
        row = User(username=username, email=email, password_hash="x",
                   role="admin" if is_platform_admin else "viewer",
                   is_admin=is_platform_admin,
                   is_platform_admin=is_platform_admin,
                   tenant_id=tenant_id,
                   tenant_role=None if is_platform_admin else "viewer")
        s.add(row)
        await s.commit()
        return int(row.id)


async def _tenant_ids(db_session) -> dict:
    from platform_core.models.tenant import Tenant

    async with db_session() as s:
        rows = (await s.execute(select(Tenant))).scalars().all()
        return {t.slug: int(t.id) for t in rows}


@pytest.fixture
def seed(db_session):
    """platform 租户 + 种子 admin + 第二平台超管（actor）+ 业务租户同名 admin"""
    state: dict = {}
    state["headers"] = make_platform_admin_headers(db_session)  # 建 platform + t04-root
    ids = asyncio.run(_tenant_ids(db_session))
    state["platform_id"] = ids["platform"]

    async def _go():
        # 种子 admin（set_admin_account 形态：platform 租户 + username=admin + 超管）
        state["seed_admin_id"] = await _add_user(
            db_session, username="admin", email="admin@example.com",
            tenant_id=state["platform_id"], is_platform_admin=True)
        # 业务租户同名 admin（防误伤对照组：跨租户 admin 不在种子保护内）
        from platform_core.models.tenant import Tenant

        async with db_session() as s:
            co = Tenant(slug="co-b", name="乙公司")
            s.add(co)
            await s.flush()
            state["co_b_id"] = int(co.id)
            await s.commit()
        state["co_admin_id"] = await _add_user(
            db_session, username="admin", email="admin@co-b.local",
            tenant_id=state["co_b_id"])

    asyncio.run(_go())
    yield state


# ---------------- GWT-94.1：种子 admin 不可删（第二超管在场） ----------------


def test_seed_admin_undeletable_even_with_second_platform_admin(db_client, db_session, seed):
    """第二平台超管在场（「最后超管」不适用）→ 删种子 admin 仍拒绝 + 中文句"""
    resp = db_client.delete(f"{USERS_URL}/{seed['seed_admin_id']}",
                            headers=seed["headers"])
    assert resp.status_code == 400
    assert resp.json()["message"] == "平台初始账号不可删除。"

    from platform_core.models.user import User

    async def _row():
        async with db_session() as s:
            return await s.get(User, seed["seed_admin_id"])

    row = asyncio.run(_row())
    assert row.deleted_at is None  # admin 保持存在（未软删）


def test_same_name_admin_in_business_tenant_still_deletable(db_client, seed):
    """跨租户同名 admin（业务租户）不受种子保护误伤：可正常软删"""
    resp = db_client.delete(f"{USERS_URL}/{seed['co_admin_id']}",
                            headers=seed["headers"])
    assert resp.status_code == 200
    assert resp.json()["data"]["deleted"] is True


def test_existing_delete_guards_still_hold(db_client, db_session, seed):
    """既有两守卫并存回归：不可删自己；不可删最后一个平台超管"""
    from platform_core.models.user import User

    async def _ids():
        async with db_session() as s:
            root = (await s.execute(
                select(User).where(User.username == "t04-root"))).scalar_one()
            return int(root.id)

    actor_id = asyncio.run(_ids())
    # 删自己（actor=t04-root）
    assert db_client.delete(f"{USERS_URL}/{actor_id}",
                            headers=seed["headers"]).status_code == 400
    # 删另一个超管后只剩一个在册超管的场景由既有套件钉住；此处种子 admin 被
    # 守卫拦截不依赖超管计数（上方用例已证）


# ---------------- GWT-94.2 / 94.3：平台租户不可改名 / 不可停用 ----------------


def test_platform_tenant_rename_rejected(db_client, db_session, seed):
    """对平台租户提交改名 → 拒绝 + 句「平台租户不可修改名称。」；名称保持"""
    resp = db_client.patch(f"{TENANTS_URL}/{seed['platform_id']}",
                           headers=seed["headers"], json={"name": "新公司名"})
    assert resp.status_code == 400
    assert resp.json()["message"] == "平台租户不可修改名称。"

    from platform_core.models.tenant import Tenant

    async def _row():
        async with db_session() as s:
            return await s.get(Tenant, seed["platform_id"])

    assert asyncio.run(_row()).name == "平台租户"


def test_platform_tenant_disable_rejected_login_unaffected(db_client, db_session, seed):
    """对平台租户提交停用 → 拒绝 + 句「平台租户不可停用。」；状态保持启用，
    平台租户名下用户的登录门（assert_tenant_active）不受该次拒绝影响（94.3）"""
    plat_user_id = asyncio.run(_add_user(
        db_session, username="plat-op", email="plat-op@t26.local",
        tenant_id=seed["platform_id"]))

    resp = db_client.patch(f"{TENANTS_URL}/{seed['platform_id']}",
                           headers=seed["headers"], json={"status": "disabled"})
    assert resp.status_code == 400
    assert resp.json()["message"] == "平台租户不可停用。"

    from platform_core.models.tenant import Tenant
    from platform_core.models.user import User
    from backend.services.tenant_expiry_service import assert_tenant_active

    async def _check():
        async with db_session() as s:
            tenant = await s.get(Tenant, seed["platform_id"])
            user = await s.get(User, plat_user_id)
            assert tenant.status == "active"  # 平台租户保持启用
            assert user.is_active is True
            await assert_tenant_active(s, int(user.tenant_id),
                                       is_platform_admin=False)  # 登录门不受影响

    asyncio.run(_check())


def test_platform_tenant_quota_edit_still_allowed(db_client, db_session, seed):
    """守卫精度：三名保护不含配额/到期编辑（运营台对平台租户仍可调，FR-102 依赖）"""
    resp = db_client.patch(f"{TENANTS_URL}/{seed['platform_id']}",
                           headers=seed["headers"],
                           json={"quota": {"spider": 5}})
    assert resp.status_code == 200

    from platform_core.models.tenant import Tenant

    async def _row():
        async with db_session() as s:
            return await s.get(Tenant, seed["platform_id"])

    assert (asyncio.run(_row()).quota or {}).get("spider") == 5


def test_regular_tenant_status_edit_unaffected(db_client, db_session, seed):
    """守卫精度：常规企业停用不受影响（运营台既有能力，GWT-95.2 前置不回退）"""
    resp = db_client.patch(f"{TENANTS_URL}/{seed['co_b_id']}",
                           headers=seed["headers"], json={"status": "disabled"})
    assert resp.status_code == 200

    from platform_core.models.tenant import Tenant

    async def _row():
        async with db_session() as s:
            return await s.get(Tenant, seed["co_b_id"])

    assert asyncio.run(_row()).status == "disabled"


# ---------------- GWT-94.4：无删除企业入口 ----------------


def test_no_tenant_delete_endpoint(app):
    """企业管理/运营台均无 DELETE /admin/tenants 端点（企业删除本波不开）"""
    from fastapi.routing import APIRoute

    deletes = [
        r.path for r in app.routes
        if isinstance(r, APIRoute) and "DELETE" in r.methods and "/admin/tenants" in r.path
    ]
    assert deletes == []


# ---------------- GWT-94.5：越权 404 同形（既有守卫核对） ----------------


def test_tenant_direct_patch_platform_is_404_shape(db_client, db_session, seed):
    """租户负责人直打企业编辑动作 → 页面不存在同形；平台租户与任何企业不变"""
    owner_headers, _tid = make_tenant_owner_headers(db_session, slug="co-owner")

    resp = db_client.patch(f"{TENANTS_URL}/{seed['platform_id']}",
                           headers=owner_headers, json={"status": "disabled"})
    assert resp.status_code == 404
    assert resp.json()["message"] == "Not Found"  # 同形，不是 403 信封

    from platform_core.models.tenant import Tenant

    async def _row():
        async with db_session() as s:
            return await s.get(Tenant, seed["platform_id"])

    assert asyncio.run(_row()).status == "active"
