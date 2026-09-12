"""T-27 企业管理增强（FR-95 / GWT-95.1/95.3/95.4/95.5/95.6/95.7 后端半）

Seam：TenantAdminService 单点（patch_tenant 扩 name 冲突域；list_tenants 行带
is_platform_default）+ user_service 建号路径（空/0 tenant_id → platform 租户）。
企业管理页与运营台同读 GET /admin/tenants（两读面同一真相）；本文件钉 API 面。
平台租户三名保护（T-26/FR-94）零回退由 test_t26_base_protection.py 钉住。
"""
import asyncio

import pytest
from sqlalchemy import select

from conftest import make_platform_admin_headers, make_tenant_owner_headers

TENANTS_URL = "/api/v1/admin/tenants"
USERS_URL = "/api/v1/admin/users"

# GWT-95.1 冲突拒绝句（字面断言；改句需同步本文件与 T-28 前端提示）
NAME_CONFLICT_MSG = "企业名称不可用: {name}"


def _rows(db_session) -> dict:
    """库级真相快照：slug → (id, name, status)"""
    from platform_core.models.tenant import Tenant

    async def _go():
        async with db_session() as s:
            rows = (await s.execute(select(Tenant))).scalars().all()
            return {t.slug: (int(t.id), t.name, t.status) for t in rows}

    return asyncio.run(_go())


def _list_row(db_client, headers, tenant_id: int) -> dict:
    """GET /admin/tenants 行（企业管理页与运营台共用的同一读面）"""
    listing = db_client.get(TENANTS_URL, headers=headers).json()["data"]
    return next(row for row in listing if row["id"] == tenant_id)


@pytest.fixture
def seed(db_session):
    """platform 租户 + 平台超管 + 两家常规企业（甲/乙公司）"""
    state: dict = {}
    state["headers"] = make_platform_admin_headers(db_session)  # 建 platform + t04-root

    async def _go():
        from platform_core.models.tenant import Tenant

        async with db_session() as s:
            co_a = Tenant(slug="co-a27", name="甲公司")
            co_b = Tenant(slug="co-b27", name="乙公司")
            s.add_all([co_a, co_b])
            await s.flush()
            state["co_a"], state["co_b"] = int(co_a.id), int(co_b.id)  # 提交前固化
            await s.commit()

    asyncio.run(_go())
    state["platform_id"] = _rows(db_session)["platform"][0]
    yield state


# ---------------- GWT-95.1：改名（成功/冲突域） ----------------


def test_gwt_95_1_rename_success_both_surfaces_same_truth(db_client, db_session, seed):
    """常规企业改名成功 → 列表（两读面共用端点）同显新名；其他企业不受影响"""
    resp = db_client.patch(f"{TENANTS_URL}/{seed['co_a']}",
                           headers=seed["headers"], json={"name": "甲公司新名"})
    assert resp.status_code == 200, resp.text

    rows = _rows(db_session)
    assert rows["co-a27"][1] == "甲公司新名"   # 库级真相
    assert rows["co-b27"][1] == "乙公司"       # 其他企业不受影响
    assert rows["platform"][1] == "平台租户"
    assert _list_row(db_client, seed["headers"], seed["co_a"])["name"] == "甲公司新名"
    assert _list_row(db_client, seed["headers"], seed["co_b"])["name"] == "乙公司"


def test_gwt_95_1_rename_conflict_with_existing_name_rejected(db_client, db_session, seed):
    """新名与既有企业名冲突 → 拒绝 + 中文说明；原名保持"""
    resp = db_client.patch(f"{TENANTS_URL}/{seed['co_a']}",
                           headers=seed["headers"], json={"name": "乙公司"})
    assert resp.status_code == 400
    assert resp.json()["message"] == NAME_CONFLICT_MSG.format(name="乙公司")
    assert _rows(db_session)["co-a27"][1] == "甲公司"
    assert _rows(db_session)["co-b27"][1] == "乙公司"


@pytest.mark.parametrize("reserved", ["平台租户", "AutoAgents"])
def test_gwt_95_1_rename_conflict_with_reserved_names(db_client, db_session, seed, reserved):
    """保留名（平台默认企业名「平台租户」/ 站点名 AutoAgents）同域拒绝（95.1 尾句）"""
    resp = db_client.patch(f"{TENANTS_URL}/{seed['co_a']}",
                           headers=seed["headers"], json={"name": reserved})
    assert resp.status_code == 400
    assert resp.json()["message"] == NAME_CONFLICT_MSG.format(name=reserved)
    assert _rows(db_session)["co-a27"][1] == "甲公司"


def test_gwt_95_1_rename_too_short_rejected(db_client, db_session, seed):
    """改名边界：名称 < 2 字符 → 422（与新建公司同口径）；原名保持"""
    resp = db_client.patch(f"{TENANTS_URL}/{seed['co_a']}",
                           headers=seed["headers"], json={"name": "甲"})
    assert resp.status_code == 422
    assert _rows(db_session)["co-a27"][1] == "甲公司"


# ---------------- GWT-95.3：平台默认租户显式化（后端半） ----------------


def test_gwt_95_3_list_marks_platform_default(db_client, db_session, seed):
    """列表行带 is_platform_default（slug=platform 推导，零 DDL）；
    任何企业名不含站点名 AutoAgents（§0.4 命名收口）"""
    listing = db_client.get(TENANTS_URL, headers=seed["headers"]).json()["data"]
    by_slug = {row["slug"]: row for row in listing}
    assert by_slug["platform"]["is_platform_default"] is True
    assert by_slug["co-a27"]["is_platform_default"] is False
    assert by_slug["co-b27"]["is_platform_default"] is False
    assert all("AutoAgents" not in row["name"] for row in listing)


# ---------------- GWT-95.4：无企业归属挂平台租户（建号路径） ----------------


def _create_user_payload(username: str, **overrides) -> dict:
    return {
        "username": username, "email": f"{username}@t27.local",
        "password": "passw0rd8", "role": "operator", **overrides,
    }


def test_gwt_95_4_user_without_tenant_lands_on_platform(db_client, seed):
    """超管建号不选归属企业 → 归属=平台租户（既有规则核对 + 钉住）"""
    resp = db_client.post(USERS_URL, headers=seed["headers"],
                          json=_create_user_payload("t27-noco"))
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["tenant_id"] == seed["platform_id"]
    assert data["tenant_name"] == "平台租户"


def test_gwt_95_4_user_with_zero_tenant_maps_to_platform(db_client, seed):
    """tenant_id=0（前端「（平台账户，不挂公司）」选项值）→ 同挂平台租户（0→platform 显式化）"""
    resp = db_client.post(USERS_URL, headers=seed["headers"],
                          json=_create_user_payload("t27-zeroco", tenant_id=0))
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["tenant_id"] == seed["platform_id"]
    assert data["tenant_name"] == "平台租户"


# ---------------- GWT-95.5：列表失败信封形态（后端半） ----------------


def test_gwt_95_5_list_failure_envelope_shape(db_client, db_session, seed, monkeypatch):
    """列表接口失败 → 统一失败信封（可判别失败 ≠ 空表；FR-84 同句式前提）"""
    from platform_core.exceptions import DatabaseException
    from backend.services.tenant_admin_service import TenantAdminService

    async def _boom(self):
        raise DatabaseException(message="数据库暂时不可用")

    monkeypatch.setattr(TenantAdminService, "list_tenants", _boom)
    resp = db_client.get(TENANTS_URL, headers=seed["headers"])
    assert resp.status_code == 500
    body = resp.json()
    assert body["success"] is False
    assert body["code"] == "DATABASE_ERROR"
    assert body["message"]            # 中文句给前端失败分支展示
    assert not isinstance(body["data"], list)  # 失败不回空列表（≠ 空表「暂无数据」）


# ---------------- GWT-95.6：越权 404 同形 ----------------


def test_gwt_95_6_tenant_admin_direct_patch_404_shape(db_client, db_session, seed):
    """租户公司管理员直打企业编辑/停用 → 页面不存在同形；任何企业名称与状态不变"""
    owner_headers, _tid = make_tenant_owner_headers(db_session, slug="co-own27")
    before = _rows(db_session)

    resp_name = db_client.patch(f"{TENANTS_URL}/{seed['co_a']}",
                                headers=owner_headers, json={"name": "越权新名"})
    resp_status = db_client.patch(f"{TENANTS_URL}/{seed['co_a']}",
                                  headers=owner_headers, json={"status": "disabled"})
    assert resp_name.status_code == 404
    assert resp_name.json()["message"] == "Not Found"   # 同形，不是 403 信封
    assert resp_status.status_code == 404
    assert _rows(db_session) == before                  # 名称与状态不变


# ---------------- GWT-95.2/95.7：停用 ⇄ 再启用（后端半 = UPDATE 成功） ----------------


def test_gwt_95_7_disable_then_reenable_roundtrip(db_client, db_session, seed):
    """常规企业停用 → 再启用（双向流转）；列表（两读面）同显"""
    disabled = db_client.patch(f"{TENANTS_URL}/{seed['co_b']}",
                               headers=seed["headers"], json={"status": "disabled"})
    assert disabled.status_code == 200
    assert _rows(db_session)["co-b27"][2] == "disabled"
    assert _list_row(db_client, seed["headers"], seed["co_b"])["status"] == "disabled"

    reenabled = db_client.patch(f"{TENANTS_URL}/{seed['co_b']}",
                                headers=seed["headers"], json={"status": "active"})
    assert reenabled.status_code == 200
    assert _rows(db_session)["co-b27"][2] == "active"
    assert _list_row(db_client, seed["headers"], seed["co_b"])["status"] == "active"
