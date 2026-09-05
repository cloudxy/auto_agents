"""平台超管用户管理 CRUD（工单：用户管理页增删改查/权限分配/公司归属）

Seam：/admin/users 端点（db_client 平台超管快照 + SQLite 真库）。
"""
import asyncio

import pytest


@pytest.fixture(autouse=True)
def _seed(db_session):
    async def _do():
        from platform_core.models.tenant import Tenant
        from platform_core.models.user import User

        async with db_session() as s:
            t = Tenant(slug="uc-co", name="测试公司甲")
            platform = Tenant(slug="platform", name="平台租户")
            s.add_all([t, platform])
            await s.flush()
            # 顺序即 id：1=uc-admin（actor，conftest 鉴权 override 的 CurrentUser.id=1）
            s.add(User(username="uc-admin", email="uc-admin@x.co", password_hash="x",
                       role="admin", is_admin=True, tenant_id=t.id, tenant_role="admin"))
            s.add(User(username="uc-op", email="uc-op@x.co", password_hash="x",
                       role="operator", tenant_id=t.id))
            # T5 后平台超管挂 platform 租户（users.tenant_id NOT NULL，NULL 语义消灭）
            s.add(User(username="uc-super", email="uc-super@x.co", password_hash="x",
                       role="admin", is_admin=True, is_platform_admin=True,
                       tenant_id=platform.id))
            await s.commit()
            STATE["tenant_id"] = t.id
    STATE = {}
    asyncio.run(_do())
    yield STATE


def test_list_users_includes_tenant_name(db_client, _seed):
    """列表带归属公司名（JOIN tenants；T5 后平台超管挂 platform 租户）"""
    resp = db_client.get("/api/v1/admin/users?limit=50")
    assert resp.status_code == 200
    rows = {u["username"]: u for u in resp.json()["data"]["items"]}
    assert rows["uc-op"]["tenant_name"] == "测试公司甲"
    assert rows["uc-admin"]["tenant_name"] == "测试公司甲"
    assert rows["uc-super"]["tenant_name"] == "平台租户"  # T5：平台超管显式挂 platform 租户


def test_create_user_with_role_and_tenant(db_client, _seed):
    """创建账户：角色 + 归属公司；密码不入响应"""
    resp = db_client.post("/api/v1/admin/users", json={
        "username": "new-op", "email": "new-op@x.co", "password": "Passw0rd!",
        "role": "viewer", "tenant_id": _seed["tenant_id"],
    })
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["role"] == "viewer" and data["tenant_name"] == "测试公司甲"
    assert "password" not in data


def test_create_user_duplicate_username_rejected(db_client, _seed):
    """同租户同名 → 400（T5 后查重按 (目标租户, username) 口径）"""
    resp = db_client.post("/api/v1/admin/users", json={
        "username": "uc-op", "email": "other@x.co", "password": "Passw0rd!",
        "role": "viewer", "tenant_id": _seed["tenant_id"]})
    assert resp.status_code == 400


def test_create_user_same_name_in_platform_tenant_allowed(db_client, _seed):
    """跨租户同名合法（T5 语义）：不带 tenant_id 落 platform 租户，与业务租户
    的 uc-op 同名不冲突（旧全局查重会误杀）"""
    resp = db_client.post("/api/v1/admin/users", json={
        "username": "uc-op", "email": "other@x.co", "password": "Passw0rd!", "role": "viewer"})
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["tenant_name"] == "平台租户" and data["is_platform_admin"] is False


def test_update_user_role(db_client, _seed):
    """权限分配：role 修改联动 is_admin/tenant_role"""
    users = {u["username"]: u for u in db_client.get("/api/v1/admin/users?limit=50").json()["data"]["items"]}
    uid = users["uc-op"]["id"]
    resp = db_client.patch(f"/api/v1/admin/users/{uid}", json={"role": "admin"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["role"] == "admin" and data["is_admin"] is True and data["tenant_role"] == "admin"


def test_update_self_demotion_rejected(db_client, _seed):
    """防自锁：不能降级自己的 admin 角色（actor=uc-admin，id=1）"""
    resp = db_client.patch("/api/v1/admin/users/1", json={"role": "viewer"})
    assert resp.status_code == 400
    assert "自锁" in resp.json()["message"] or "降级" in resp.json()["message"]


def test_delete_user_soft_and_guardrails(db_client, _seed):
    """软删除：列表消失；不可删自己（actor id=1）；不可删最后一个平台超管"""
    users = {u["username"]: u for u in db_client.get("/api/v1/admin/users?limit=50").json()["data"]["items"]}

    # 删自己被拒（actor=uc-admin id=1）
    assert db_client.delete("/api/v1/admin/users/1").status_code == 400
    # 最后一个平台超管被拒（uc-super 是库内唯一超管）
    assert db_client.delete(f"/api/v1/admin/users/{users['uc-super']['id']}").status_code == 400

    # 普通用户软删成功
    uid = users["uc-op"]["id"]
    assert db_client.delete(f"/api/v1/admin/users/{uid}").status_code == 200
    names = [u["username"] for u in db_client.get("/api/v1/admin/users?limit=50").json()["data"]["items"]]
    assert "uc-op" not in names
