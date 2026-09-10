"""T10 回归沉淀：高危缺陷修复的复现用例（历史上无回归佐证的三类中的后端两类）

缺陷 commit 标注（用例名内可检索）：
- 789165e fix(saas): 运营管理 403——admin 归位 default 租户 owner + 登录快照
  下发租户维度。代码增量 = 登录响应 data 携带 tenant_id/tenant_role（与 JWT
  payload 同源）；403 现象边界 = require_tenant_manager 拒绝 tenant_role 为
  None 的纯平台超管（当年 admin 种子 tenant_id=NULL 即落此分支）。
- 0e0aaf8 fix(db): 资产目录 500——去除 MySQL 不支持的 NULLS LAST 语法
  （SQLite 测试库放行、MySQL 1064）。回归钉子 = 生产排序语句在 MySQL 方言
  编译产物不得含 NULLS LAST/FIRST（无需真库即可拦截同类回归）。
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.api.v1.members import require_tenant_manager
from backend.app.api.deps import CurrentUser
from backend.repositories.skill_repository import SkillRepository
from backend.services.capability_service import CapabilityService
from backend.utils.auth import get_password_hash
from platform_core.exceptions import AuthorizationException
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

from conftest import mysql_fidelity_enabled

# ---------------------------------------------------------------------------
# 789165e：登录快照下发租户维度
# ---------------------------------------------------------------------------


async def _seed_tenant_owner(db_session) -> dict:
    """种 default 租户 + owner 用户（789165e 修复后 admin 的标准形态）"""
    async with db_session() as s:
        tenant = Tenant(slug="reg789165e", name="回归租户")
        s.add(tenant)
        await s.flush()
        user = User(
            username="reg-owner-789165e",
            email="reg-owner-789165e@test.local",
            password_hash=get_password_hash("reg-pass-123"),
            role="admin", tenant_id=tenant.id, tenant_role="owner",
        )
        s.add(user)
        await s.commit()
        return {"tenant_id": tenant.id, "user_id": user.id}


def test_login_snapshot_carries_tenant_fields(db_client, db_engine, db_session):
    """789165e：登录响应 data 必含 tenant_id/tenant_role（前端菜单可见性数据源）

    修复前响应缺失这两个字段 → 纯平台超管前端判定 tenantBound 恒 false →
    成员管理/用量看板菜单隐藏逻辑失去数据基础（菜单边界同 commit 引入）。
    """
    state = asyncio.run(_seed_tenant_owner(db_session))
    resp = db_client.post(
        "/api/v1/auth/login",
        json={"username": "reg-owner-789165e", "password": "reg-pass-123"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["tenant_id"] == state["tenant_id"]
    assert data["tenant_role"] == "owner"


# ---------------------------------------------------------------------------
# 789165e：403 现象边界——require_tenant_manager 权限矩阵
# ---------------------------------------------------------------------------


def _user_with(tenant_role: str | None) -> CurrentUser:
    return CurrentUser(
        id=7, username="u7", role="admin",
        tenant_id=None if tenant_role is None else 1,
        tenant_role=tenant_role,
    )


@pytest.mark.asyncio
async def test_tenant_manager_guard_matrix_789165e():
    """789165e：require_tenant_manager 逐格——owner/admin 放行；operator/viewer/
    None（纯平台超管 tenant_role=NULL，当年 403 的根因形态）拒绝且状态不变"""
    for allowed in ("owner", "admin"):
        user = await require_tenant_manager(user=_user_with(allowed))
        assert user.tenant_role == allowed

    for denied in ("operator", "viewer", None):
        with pytest.raises(AuthorizationException):
            await require_tenant_manager(user=_user_with(denied))


# ---------------------------------------------------------------------------
# 0e0aaf8：MySQL 方言——排序语句不得携带 NULLS LAST/FIRST
# ---------------------------------------------------------------------------


def _mysql_compiled(stmt) -> str:
    from sqlalchemy.dialects import mysql

    return str(stmt.compile(dialect=mysql.dialect()))


@pytest.mark.asyncio
async def test_skill_repository_sort_compiles_on_mysql_0e0aaf8():
    """0e0aaf8：list_skills 生产排序语句 MySQL 方言编译产物无 NULLS LAST/FIRST

    修复前 order_by(sort_col.desc().nullslast()) 在 SQLite 放行、MySQL 1064
    （资产列表 500）。捕获方式：mock session 拦截生产语句（非测试侧重构），
    若回归 nullslast()，MySQL 编译产物立即出现 NULLS LAST → 用例红。
    """
    session = MagicMock()
    rows_mock = MagicMock()
    rows_mock.scalar_one.return_value = 0
    rows_mock.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=rows_mock)

    repo = SkillRepository(session)
    await repo.list_skills(sort="updated_at")

    assert session.execute.await_count >= 1
    stmt = session.execute.await_args_list[-1].args[0]
    compiled = _mysql_compiled(stmt).upper()
    assert "NULLS LAST" not in compiled, "0e0aaf8 回归：排序语句携带 MySQL 不支持的 NULLS LAST"
    assert "NULLS FIRST" not in compiled, "0e0aaf8 回归：排序语句携带 MySQL 不支持的 NULLS FIRST"
    assert "ORDER BY" in compiled  # 反空心：确认确实断言到了排序子句


@pytest.mark.asyncio
async def test_capability_service_sort_compiles_on_mysql_0e0aaf8():
    """0e0aaf8：capability_service.list_assets 生产排序语句同口径断言"""
    session = MagicMock()
    rows_mock = MagicMock()
    rows_mock.scalar_one.return_value = 0
    rows_mock.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=rows_mock)

    svc = CapabilityService(session)
    await svc.list_assets()

    stmt = session.execute.await_args_list[-1].args[0]
    compiled = _mysql_compiled(stmt).upper()
    assert "NULLS LAST" not in compiled
    assert "NULLS FIRST" not in compiled
    assert "ORDER BY" in compiled


@pytest.mark.skipif(
    not mysql_fidelity_enabled(),
    reason="需真库验证：MySQL 方言下 NULL 排序语义往返（CI MYSQL_FIDELITY 通道执行）",
)
def test_null_aware_sort_roundtrip_mysql_fidelity(db_client, admin_client, db_engine, db_session):
    """0e0aaf8 保真通道：真 MySQL 上 NULL updated_at 行参与排序不 500 且 NULL 排最后

    MySQL DESC 默认 NULL 在最后（与修复后的语义等价断言）；SQLite 通道
    跳过（SQLite DESC 同样 NULL 最后，测不出方言差异——这正是当年盲区）。
    """
    from platform_core.models.capability import CapabilityAsset

    async def _seed_and_query():
        from sqlalchemy import update as sa_update

        async with db_session() as s:
            s.add_all([
                CapabilityAsset(asset_type="plugin", name="t10-null-ts", status="active"),
                CapabilityAsset(asset_type="plugin", name="t10-with-ts", status="active"),
            ])
            await s.flush()
            await s.execute(
                sa_update(CapabilityAsset).where(CapabilityAsset.name == "t10-null-ts")
                .values(updated_at=None))
            await s.commit()

        resp = admin_client.get("/api/v1/capabilities", params={"type": "plugin"})
        assert resp.status_code == 200, resp.text
        items = resp.json()["data"]["items"]
        names = [item["name"] for item in items]
        assert "t10-with-ts" in names
        if "t10-null-ts" in names:
            # NULL 行存在时必须排在最后（MySQL DESC 语义）
            assert names.index("t10-null-ts") == len(names) - 1

    asyncio.run(_seed_and_query())
