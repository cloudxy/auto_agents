"""B1a 零覆盖路由清剿（RBAC 域）：/rbac/departments CRUD

覆盖路由清单（本轮缺口 = 全部 4 条，既有测试零 HTTP 引用）：
- GET    /api/v1/rbac/departments            部门列表（按租户；软删行排除；含成员计数）
- POST   /api/v1/rbac/departments            创建部门（租户内名唯一；租户须存在）
- PUT    /api/v1/rbac/departments/{id}       编辑部门（改名/说明）
- DELETE /api/v1/rbac/departments/{id}       软删部门（成员 department_id 置空回退未分组）

用例推导口径（标准 = 路由 docstring + DepartmentCreateRequest 契约 + 模型约束）：
- 正常路径断言响应结构关键字段（信封 code + data 字段），不只 200
- 破坏性操作（DELETE）断言库内副作用：软删（deleted_at 置位、行仍在）、
  成员回退未分组（users.department_id → NULL）、列表排除
- 唯一名契约按租户为界：同租户重名 400 / 跨租户同名 201 / 软删后同名可重建
  （alive_flag 生成列唯一键——SQLite 与 MySQL 方言均支持，行为需真库复验）
- 边界：name 长度 1/64（界上）与 0/65（界外）；缺 tenant_id 查询参数
- 权限矩阵：4 路由 × 匿名 401 / viewer 403（require_admin 守卫）
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select

from platform_core.models.department import Department
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

DEPT_URL = "/api/v1/rbac/departments"

# 有效载荷模板（name 长度 2，典型值；边界值各用例显式给）
_VALID = {"tenant_id": None, "name": "数据组", "description": "采编"}


@pytest.fixture
def _tenants(db_session):
    """两个租户（A/B）——唯一名契约按租户为界的判定基础；返回 {A, B} 的 id"""
    state: dict[str, int] = {}

    async def _do():
        async with db_session() as s:
            a = Tenant(slug="b1a-co-a", name="公司甲")
            b = Tenant(slug="b1a-co-b", name="公司乙")
            s.add_all([a, b])
            await s.flush()
            state["A"], state["B"] = a.id, b.id
            await s.commit()

    asyncio.run(_do())
    return state


def _payload(tenants: dict, name: str = "数据组") -> dict:
    return {"tenant_id": tenants["A"], "name": name, "description": "采编"}


async def _dept_rows(db_session) -> list[Department]:
    async with db_session() as s:
        return list((await s.execute(select(Department))).scalars().all())


# ---------------------------------------------------------------------------
# POST /api/v1/rbac/departments
# ---------------------------------------------------------------------------


def test_create_department_ok(db_client, admin_client, db_session, _tenants):
    """创建：201 CREATED + data 含 id/name（路由契约仅回这两字段）；库内行持久化"""
    resp = admin_client.post(DEPT_URL, json=_payload(_tenants, name="x" * 64))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == "CREATED"
    assert set(body["data"].keys()) == {"id", "name"}
    assert body["data"]["name"] == "x" * 64  # name 长度界上（max=64）合法
    assert isinstance(body["data"]["id"], int)

    rows = asyncio.run(_dept_rows(db_session))
    assert len(rows) == 1  # 副作用断言：恰好一条
    assert rows[0].tenant_id == _tenants["A"]  # 归属租户经库内验证
    assert rows[0].description == "采编"
    assert rows[0].deleted_at is None


def test_create_department_name_length_1_ok(db_client, admin_client, _tenants):
    """name 长度界上另一端（min=1）：单字符合法"""
    resp = admin_client.post(DEPT_URL, json=_payload(_tenants, name="组"))
    assert resp.status_code == 201


def test_create_department_dup_in_tenant_400(db_client, admin_client, db_session, _tenants):
    """同租户重名 → 400 BUSINESS_ERROR，且无第二条落库"""
    assert admin_client.post(DEPT_URL, json=_payload(_tenants)).status_code == 201
    dup = admin_client.post(DEPT_URL, json=_payload(_tenants, name="数据组"))
    assert dup.status_code == 400
    assert dup.json()["code"] == "BUSINESS_ERROR"
    assert "部门已存在" in dup.json()["message"]

    rows = asyncio.run(_dept_rows(db_session))
    assert len(rows) == 1  # 拒绝路径零副作用


def test_create_department_same_name_other_tenant_201(db_client, admin_client, db_session, _tenants):
    """跨租户同名合法（唯一名契约以租户为界）；归属经库内验证"""
    assert admin_client.post(DEPT_URL, json=_payload(_tenants)).status_code == 201
    cross = admin_client.post(
        DEPT_URL, json={"tenant_id": _tenants["B"], "name": "数据组"})
    assert cross.status_code == 201, cross.text

    async def _check():
        async with db_session() as s:
            return list((await s.execute(
                select(Department).where(Department.tenant_id == _tenants["B"])
            )).scalars().all())

    rows = asyncio.run(_check())
    assert len(rows) == 1 and rows[0].name == "数据组"


def test_create_department_unknown_tenant_422(db_client, admin_client, db_session):
    """tenant 不存在 → 422 VALIDATION_ERROR（field=tenant_id），零落库"""
    resp = admin_client.post(DEPT_URL, json={"tenant_id": 99999999, "name": "幽灵组"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["data"]["field"] == "tenant_id"

    assert asyncio.run(_dept_rows(db_session)) == []


@pytest.mark.parametrize("payload,field", [
    ({"tenant_id": 1}, "name"),                        # 缺 name
    ({"tenant_id": 1, "name": ""}, "name"),            # 空串（min=1 界外）
    ({"tenant_id": 1, "name": "x" * 65}, "name"),      # 超长（max=64 界外）
    ({"name": "无租户"}, "tenant_id"),                  # 缺 tenant_id
])
def test_create_department_validation_422(db_client, admin_client, db_session, payload, field):
    """请求体校验 422（FastAPI 层），零落库"""
    resp = admin_client.post(DEPT_URL, json=payload)
    assert resp.status_code == 422, resp.text
    assert field in resp.text
    assert asyncio.run(_dept_rows(db_session)) == []


# ---------------------------------------------------------------------------
# GET /api/v1/rbac/departments
# ---------------------------------------------------------------------------


def test_list_departments_with_member_count(db_client, admin_client, db_session, _tenants):
    """列表：含成员计数；软删行排除；空部门计数 0"""
    async def _seed():
        async with db_session() as s:
            d1 = Department(tenant_id=_tenants["A"], name="数据组")
            d2 = Department(tenant_id=_tenants["A"], name="运营组")
            dead = Department(tenant_id=_tenants["A"], name="已删组",
                              deleted_at=func.now())
            s.add_all([d1, d2, dead])
            await s.flush()
            s.add(User(username="b1a-member", email="m@b1a.co", password_hash="x",
                       role="operator", tenant_id=_tenants["A"], department_id=d1.id))
            await s.commit()

    asyncio.run(_seed())

    resp = admin_client.get(DEPT_URL, params={"tenant_id": _tenants["A"]})
    assert resp.status_code == 200, resp.text
    rows = {r["name"]: r for r in resp.json()["data"]}
    assert set(rows) == {"数据组", "运营组"}  # 软删行排除
    assert rows["数据组"]["member_count"] == 1
    assert rows["运营组"]["member_count"] == 0
    assert rows["数据组"]["description"] is None  # 结构关键字段在位


def test_list_departments_empty(db_client, admin_client, _tenants):
    """无部门租户 → 200 + 空列表（空输入边界）"""
    resp = admin_client.get(DEPT_URL, params={"tenant_id": _tenants["B"]})
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_list_departments_missing_tenant_id_422(admin_client):
    """缺必填查询参数 tenant_id → 422"""
    resp = admin_client.get(DEPT_URL)
    assert resp.status_code == 422
    assert "tenant_id" in resp.text


# ---------------------------------------------------------------------------
# PUT /api/v1/rbac/departments/{id}
# ---------------------------------------------------------------------------


def _create_dept(admin_client, tenants, name="数据组") -> int:
    resp = admin_client.post(DEPT_URL, json=_payload(tenants, name=name))
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


def test_update_department_ok(db_client, admin_client, db_session, _tenants):
    """编辑：200 UPDATED + 回显变更字段；库内已更新"""
    did = _create_dept(admin_client, _tenants)
    resp = admin_client.put(f"{DEPT_URL}/{did}",
                            json={"name": "数据二组", "description": "改"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "UPDATED"
    assert body["data"]["name"] == "数据二组"
    assert body["data"]["description"] == "改"

    async def _check():
        async with db_session() as s:
            return (await s.execute(select(Department).where(Department.id == did))).scalar_one()

    row = asyncio.run(_check())
    assert row.name == "数据二组" and row.description == "改"


def test_update_department_not_found_404(admin_client):
    resp = admin_client.put(f"{DEPT_URL}/99999999", json={"name": "无"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# DELETE /api/v1/rbac/departments/{id}
# ---------------------------------------------------------------------------


def test_delete_department_soft_and_member_fallback(db_client, admin_client, db_session, _tenants):
    """软删三断言：deleted_at 置位（行仍在）；成员回退未分组；列表排除"""
    did = _create_dept(admin_client, _tenants)

    async def _attach():
        async with db_session() as s:
            s.add(User(username="b1a-fallback", email="f@b1a.co", password_hash="x",
                       role="viewer", tenant_id=_tenants["A"], department_id=did))
            await s.commit()

    asyncio.run(_attach())

    resp = admin_client.delete(f"{DEPT_URL}/{did}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"] == {"id": did, "deleted": True}

    async def _check():
        async with db_session() as s:
            row = (await s.execute(
                select(Department).where(Department.id == did))).scalar_one()
            member = (await s.execute(
                select(User).where(User.username == "b1a-fallback"))).scalar_one()
            return row, member

    row, member = asyncio.run(_check())
    assert row.deleted_at is not None  # 软删：行未物理删除
    assert member.department_id is None  # 成员回退未分组

    listed = admin_client.get(DEPT_URL, params={"tenant_id": _tenants["A"]}).json()["data"]
    assert listed == []  # 列表排除软删行


def test_delete_then_recreate_same_name_201(db_client, admin_client, _tenants):
    """软删后同名可重建（alive_flag 唯一键：软删行脱离约束；组织重组高频路径）
    注：alive_flag 为生成列，SQLite/MySQL 方言均支持，行为建议 MYSQL_FIDELITY=1 复验"""
    did = _create_dept(admin_client, _tenants, name="重组组")
    assert admin_client.delete(f"{DEPT_URL}/{did}").status_code == 200
    again = admin_client.post(DEPT_URL, json=_payload(_tenants, name="重组组"))
    assert again.status_code == 201, again.text  # 同名重建不被软删行挡


def test_delete_department_not_found_404(admin_client):
    resp = admin_client.delete(f"{DEPT_URL}/99999999")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# 权限矩阵：4 路由 × 匿名 401 / viewer 403（require_admin 守卫存在性证明）
# ---------------------------------------------------------------------------

_VALID_BODY = {"tenant_id": 1, "name": "probe", "description": None}


def test_departments_anonymous_401(client):
    """匿名直调四操作 → 401（AUTH_FAILED；请求体给合法值，确保先过校验再撞守卫）"""
    assert client.get(DEPT_URL, params={"tenant_id": 1}).status_code == 401
    assert client.post(DEPT_URL, json=_VALID_BODY).status_code == 401
    assert client.put(f"{DEPT_URL}/1", json={"name": "probe"}).status_code == 401
    assert client.delete(f"{DEPT_URL}/1").status_code == 401


def test_departments_viewer_403(viewer_client, db_session):
    """viewer 直调四操作（绕过前端隐藏入口）→ 403，且零写入"""
    assert viewer_client.get(DEPT_URL, params={"tenant_id": 1}).status_code == 403
    assert viewer_client.post(DEPT_URL, json=_VALID_BODY).status_code == 403
    assert viewer_client.put(f"{DEPT_URL}/1", json={"name": "probe"}).status_code == 403
    assert viewer_client.delete(f"{DEPT_URL}/1").status_code == 403
    assert asyncio.run(_dept_rows(db_session)) == []  # 越权路径零副作用
