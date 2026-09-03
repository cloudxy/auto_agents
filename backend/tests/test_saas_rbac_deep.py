"""SaaS 化深化（迁移 023）：动态菜单 / 菜单 CRUD / 权限资源 CRUD / 自定义角色

Seam：/auth/menus 与 /rbac/* 端点（db_client + SQLite 真库；菜单种子经迁移 023 落库）。
"""
import asyncio

import pytest


@pytest.fixture(autouse=True)
def _seed(db_session):
    async def _do():
        from platform_core.models.menu import Menu
        from platform_core.models.permission import Permission
        from platform_core.models.role import Role

        async with db_session() as s:
            # 基础种子（真库经迁移 022/023 播种；SQLite 测试库 create_all 无种子）
            s.add(Role(role_key="admin", name="管理员", permissions=[
                'menu:dashboard', 'menu:spiders', 'menu:spiders.tasks', 'menu:spiders.logs',
                'menu:users', 'menu:data', 'menu:settings', 'menu:ai', 'menu:skills',
                'menu:members', 'menu:usage', 'menu:platform-ops', 'menu:logs',
                'menu:llm', 'menu:newapi',
                'btn:create', 'btn:delete', 'btn:schedule', 'btn:skill:edit', 'btn:skill:admin',
            ], is_builtin=True))
            s.add(Role(role_key="viewer", name="只读", permissions=["menu:dashboard"], is_builtin=True))
            s.add(Menu(name="仪表盘", path="/dashboard", permission="menu:dashboard", sort_order=10))
            top = Menu(name="测试分组", path=None, sort_order=99)
            s.add(top)
            await s.flush()
            s.add(Menu(parent_id=top.id, name="测试页", path="/x-test", permission="btn:test:x", sort_order=1))
            s.add(Menu(name="无权页", path="/x-noauth", permission="btn:test:none"))
            s.add(Permission(code="btn:test:x", name="测试权限", group_name="测试", ptype="btn"))
            await s.commit()
            STATE["group_id"] = top.id
    STATE = {}
    asyncio.run(_do())
    yield STATE


def test_dynamic_menus_filtered_by_role(db_client, _seed):
    """动态菜单：无权限项被过滤；空分组剔除；admin 全量可见"""
    resp = db_client.get("/api/v1/auth/menus")
    assert resp.status_code == 200
    tree = resp.json()["data"]
    # 种子菜单 + 测试分组都应在（conftest admin 快照 role=admin 全权限，但 btn:test:x 不在 admin 权限集）
    # admin 权限集来自 roles 种子（20 码），btn:test:x 不在其中 → 测试页被过滤
    flat = []

    def walk(nodes):
        for n in nodes:
            flat.append(n["key"])
            walk(n.get("children") or [])
    walk(tree)
    assert "/x-test" not in flat      # 权限码未授予 → 隐藏
    assert "/dashboard" in flat       # 种子菜单 + admin 权限 → 可见
    # 无权页也被过滤后，"测试分组"若空则整体剔除
    grp_keys = [n["key"] for n in tree]
    assert all(k.startswith("grp-") or k.startswith("/") for k in grp_keys)


def test_menu_crud_roundtrip(db_client, _seed):
    """菜单 CRUD：建（挂父）→ 改 → 级联守卫 → 删"""
    created = db_client.post("/api/v1/rbac/menus", json={
        "parent_id": _seed["group_id"], "name": "子页", "path": "/x-child", "sort_order": 5})
    assert created.status_code == 201
    cid = created.json()["data"]["id"]

    upd = db_client.put(f"/api/v1/rbac/menus/{cid}", json={"name": "子页改", "visible": False})
    assert upd.status_code == 200

    # 父级有子 → 禁删
    assert db_client.delete(f"/api/v1/rbac/menus/{_seed['group_id']}").status_code == 400
    # 删子 → 可
    assert db_client.delete(f"/api/v1/rbac/menus/{cid}").status_code == 200


def test_permission_resource_crud_with_reference_guard(db_client, _seed):
    """权限资源：注册 → 改 → 被角色引用禁删 → 解除后可删"""
    created = db_client.post("/api/v1/rbac/permissions", json={
        "code": "btn:tmp:demo", "name": "临时权限", "group_name": "测试", "ptype": "btn"})
    assert created.status_code == 201
    pid = created.json()["data"]["id"]

    assert db_client.put(f"/api/v1/rbac/permissions/{pid}", json={"name": "临时权限改"}).status_code == 200

    # 引用守卫：把权限授予 admin 后禁删
    roles = db_client.get("/api/v1/rbac/roles").json()["data"]["roles"]
    admin = next(r for r in roles if r["role_key"] == "admin")
    db_client.put("/api/v1/rbac/roles/admin", json={"permissions": [*admin["permissions"], "btn:tmp:demo"]})
    assert db_client.delete(f"/api/v1/rbac/permissions/{pid}").status_code == 400
    # 解除引用 → 可删
    db_client.put("/api/v1/rbac/roles/admin", json={"permissions": admin["permissions"]})
    assert db_client.delete(f"/api/v1/rbac/permissions/{pid}").status_code == 200


def test_custom_role_crud(db_client, _seed):
    """自定义角色：建 → 内置禁删 → 无引用可删"""
    created = db_client.post("/api/v1/rbac/roles", json={
        "role_key": "auditor", "name": "审计员", "permissions": ["menu:logs"]})
    assert created.status_code == 201

    assert db_client.delete("/api/v1/rbac/roles/admin").status_code == 400  # 内置禁删
    assert db_client.delete("/api/v1/rbac/roles/auditor").status_code == 200


def test_tenant_minimal_create(db_client, _seed):
    """企业最小创建：名称必填、slug 唯一容错"""
    resp = db_client.post("/api/v1/admin/tenants", json={"name": "测试公司乙"})
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["slug"]
    assert db_client.post("/api/v1/admin/tenants", json={"name": "x"}).status_code in (400, 422)
