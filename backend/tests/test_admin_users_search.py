"""用户管理服务端检索（决策 D11，连带 BUG-40；2026-09-29「按照建议做」）

原先搜索 / 角色 / 公司 / 部门只在当前页本地过滤，总数却是全库——第 2 页以后的用户搜不到。
现在全部走服务端：total 与筛选一致，跨页可搜到。
- q：登录名或邮箱包含（% _ 按字面匹配，不当通配符）
- role / tenant_id / department_id：精确匹配
- status：active=在职（含停用）；enabled=在职·激活；disabled=已停用；deleted=已删除
"""
from __future__ import annotations

import asyncio

from conftest import make_platform_admin_headers
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

USERS = "/api/v1/admin/users"


def _seed(db_session) -> tuple[int, int]:
    async def _go():
        async with db_session() as s:
            a = Tenant(slug="d11-a", name="甲公司")
            b = Tenant(slug="d11-b", name="乙公司")
            s.add_all([a, b])
            await s.flush()
            for i in range(25):  # 超过一页（20），最后几位只在第 2 页
                s.add(User(username=f"d11-op-{i:02d}", email=f"op{i:02d}@d11.test", password_hash="x",
                           role="operator", tenant_id=a.id, tenant_role="operator", is_active=True))
            s.add(User(username="d11-late", email="needle.findme@d11.test", password_hash="x",
                       role="viewer", tenant_id=b.id, tenant_role="viewer", is_active=True, department_id=7))
            s.add(User(username="d11-off", email="off@d11.test", password_hash="x",
                       role="viewer", tenant_id=b.id, tenant_role="viewer", is_active=False))
            s.add(User(username="d11_100%", email="pct@d11.test", password_hash="x",
                       role="operator", tenant_id=b.id, tenant_role="operator", is_active=True))
            await s.commit()
            return int(a.id), int(b.id)
    return asyncio.run(_go())


def _get(client, headers, **params):
    resp = client.get(USERS, headers=headers, params={"limit": 20, **params})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    return data["total"], [u["username"] for u in data["items"]]


def test_search_by_email_finds_user_beyond_first_page(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    _seed(db_session)
    assert _get(db_client, pa, q="needle.findme") == (1, ["d11-late"])
    assert _get(db_client, pa, q="NEEDLE") == (1, ["d11-late"])  # 大小写不敏感


def test_role_tenant_department_filters_are_server_side(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    a, b = _seed(db_session)
    total, names = _get(db_client, pa, tenant_id=a)
    assert total == 25 and len(names) == 20  # total 是筛选后的全量，不是本页
    total, names = _get(db_client, pa, role="viewer", tenant_id=b)
    assert total == 2 and set(names) == {"d11-late", "d11-off"}
    assert _get(db_client, pa, department_id=7) == (1, ["d11-late"])


def test_status_enabled_excludes_disabled(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    _a, b = _seed(db_session)
    total, names = _get(db_client, pa, tenant_id=b, status="enabled")
    assert "d11-off" not in names and total == 2
    assert _get(db_client, pa, tenant_id=b, status="disabled") == (1, ["d11-off"])


def test_like_wildcards_are_literal(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    _seed(db_session)
    assert _get(db_client, pa, q="%") == (1, ["d11_100%"])
    assert _get(db_client, pa, q="d11_1") == (1, ["d11_100%"])
