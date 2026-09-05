"""S1-5 R13 越权测试套件（工单 35）：A 租户访问 B 租户资源全 403/404

Seam（工单预确认）：db_client（真实 JWT → 中间件 → tenant_scope → 行级隔离全链路）。
覆盖资源类：spiders/tasks / spiders/definitions / spiders/templates / ai / llm/providers
（skills 为平台级豁免——全租户共享只读，不在越权面）。

T5 扩容：users/members 越权（User 继承 TenantMixin 后自动过滤收口）+
中间件收紧（NULL 租户非平台超管 token → 401）+ deps 链伪造租户 token → 401。
"""
import asyncio

import pytest
from sqlalchemy import select, update

from backend.services.auth_service import AuthService
from platform_core.models.llm_provider import LlmProvider
from platform_core.models.spider_definition import SpiderDefinition
from platform_core.models.spider_task import SpiderTask
from platform_core.models.task_template import TaskTemplate
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

TOKENS: dict[str, str] = {}
_SUFFIX = 0


async def _seed(db_session) -> None:
    global _SUFFIX
    _SUFFIX += 1
    sfx = _SUFFIX
    async with db_session() as s:
        t1 = Tenant(slug=f"alpha-{sfx}", name="A")
        t2 = Tenant(slug=f"beta-{sfx}", name="B")
        s.add_all([t1, t2])
        await s.flush()
        s.add_all([
            User(username=f"a-owner-{sfx}", email=f"a{sfx}@x.local", password_hash="x",
                 role="admin", tenant_id=t1.id, tenant_role="owner"),
            User(username=f"b-owner-{sfx}", email=f"b{sfx}@x.local", password_hash="x",
                 role="admin", tenant_id=t2.id, tenant_role="owner"),
        ])
        # B 租户的私有数据（A 不应可见）
        s.add_all([
            SpiderTask(spider_name=f"b-task-{sfx}", tenant_id=t2.id, params="{}"),
            SpiderDefinition(name=f"b-def-{sfx}", title="B Def", tenant_id=t2.id),
            TaskTemplate(name=f"b-tpl-{sfx}", spider_name=f"b-spid-{sfx}", params="{}", tenant_id=t2.id),
            LlmProvider(name=f"b-provider-{sfx}", provider_type="openai_compatible",
                        base_url="https://b", model="m", tenant_id=t2.id),
        ])
        await s.commit()

        svc = AuthService(s)
        for label, tenant in (("a", t1), ("b", t2)):
            username = f"{label}-owner-{sfx}"
            user = (await s.execute(select(User).where(User.username == username))).scalar_one()
            token = await svc.create_token({
                "id": user.id, "username": username, "is_admin": False, "role": "admin",
                "tenant_id": tenant.id, "tenant_role": "owner",
                "is_platform_admin": False,
            })
            TOKENS["a"] = token.access_token if label == "a" else TOKENS.get("a")
            TOKENS["b"] = token.access_token if label == "b" else TOKENS.get("b")
        return {"a": t1.id, "b": t2.id, "sfx": sfx}


@pytest.fixture(autouse=True)
def seeded(db_session):
    asyncio.run(_seed(db_session))
    yield


def _auth(label: str) -> dict:
    return {"Authorization": f"Bearer {TOKENS[label]}"}


def test_a_cannot_see_b_tasks(db_client):
    resp = db_client.get("/api/v1/spiders/tasks", headers=_auth("a"))
    assert resp.status_code == 200
    body = resp.json()
    items = body.get("data", {}).get("items") or body.get("data", {}).get("list") or []
    assert all("b-task-" not in str(it) for it in items)


def test_a_cannot_see_b_definitions(db_client):
    resp = db_client.get("/api/v1/spiders/registry", headers=_auth("a"))
    assert resp.status_code == 200
    assert "b-def-" not in resp.text


def test_a_cannot_see_b_providers(db_client):
    resp = db_client.get("/api/v1/llm/providers", headers=_auth("a"))
    assert resp.status_code == 200
    assert "b-provider-" not in resp.text


def test_b_sees_own_data(db_client):
    """正向对照：B 能看到自己的数据（隔离不是一刀切不可见）"""
    resp = db_client.get("/api/v1/spiders/registry", headers=_auth("b"))
    assert resp.status_code == 200
    assert "b-def" in resp.text


def test_platform_scope_sees_all(db_client, db_engine, db_session):
    """平台超管（platform_scope）跨租户可见（运营视角）"""
    async def _go():
        async with db_session() as s:
            # T5 后平台超管挂 platform 租户（users.tenant_id NOT NULL）
            platform = Tenant(slug="platform", name="平台租户")
            s.add(platform)
            await s.flush()
            s.add(User(username="root", email="root@x.local", password_hash="x",
                       role="admin", tenant_id=platform.id, tenant_role=None,
                       is_platform_admin=True))
            await s.commit()
            root = (await s.execute(select(User).where(User.username == "root"))).scalar_one()
            return await AuthService(s).create_token({
                "id": root.id, "username": "root", "is_admin": True, "role": "admin",
                "tenant_id": None, "tenant_role": None, "is_platform_admin": True,
            })

    token = asyncio.run(_go())
    resp = db_client.get("/api/v1/spiders/registry", headers={"Authorization": f"Bearer {token.access_token}"})
    assert resp.status_code == 200
    assert "b-def-" in resp.text


# ---------------- T5 扩容：users/members 越权 + 中间件收紧 ----------------


def test_a_cannot_see_b_users_in_members(db_client):
    """A 租户 owner 看 /members：B 租户用户不可见（MemberService 显式条件
    + TenantMixin 自动过滤双保险，T5 后即使手写条件漏掉也被兜住）"""
    resp = db_client.get("/api/v1/members", headers=_auth("a"))
    assert resp.status_code == 200
    usernames = [m["username"] for m in resp.json()["data"]]
    assert any(u.startswith("a-owner-") for u in usernames), "A 应看到本租户成员"
    assert all(not u.startswith("b-owner-") for u in usernames), "B 用户不得出现在 A 的成员列表"


def test_a_cannot_see_b_users_in_admin_users(db_client):
    """/admin/users（用户管理页，A owner role=admin 可过角色守卫）：
    TenantMixin 自动过滤生效——A 只见本租户用户，B 用户不可见"""
    resp = db_client.get("/api/v1/admin/users?limit=100", headers=_auth("a"))
    assert resp.status_code == 200
    usernames = [u["username"] for u in resp.json()["data"]["items"]]
    assert any(u.startswith("a-owner-") for u in usernames), "A 应看到本租户用户（正向对照）"
    assert all(not u.startswith("b-owner-") for u in usernames), "B 用户不得出现在 A 的用户列表"


def test_null_tenant_non_platform_token_rejected(db_client, db_session):
    """中间件收紧（T5 决策 B）：非平台超管且 tenant_id=NULL 的 token → 401。

    旧条件 `is_platform_admin OR not tenant_id` 下此类 token 自动获得
    platform_scope（公开注册 NULL 账号=任意人造平台态）；收紧后 NULL 兜底消失。
    """
    async def _go():
        async with db_session() as s:
            return await AuthService(s).create_token({
                "id": 42, "username": "null-tenant-user", "is_admin": False,
                "role": "viewer", "tenant_id": None, "tenant_role": "viewer",
                "is_platform_admin": False,
            })

    token = asyncio.run(_go())
    resp = db_client.get("/api/v1/spiders/tasks",
                         headers={"Authorization": f"Bearer {token.access_token}"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_FAILED"


def test_forged_tenant_token_cannot_impersonate(db_client, db_session):
    """deps 链收紧（T5 决策 C）：伪造 token（B 用户 user_id + A 租户 tenant_id）。

    User 继承 TenantMixin 后，get_current_user 的 session.get(User, id) 在
    tenant_scope(A) 下被注入过滤——B 行租户不匹配查不到 → 401（旧行为是
    静默取 DB 行放行，语义更严属修复非回归）。
    """

    async def _ids():
        async with db_session() as s:
            rows = (await s.execute(
                select(User.username, User.id).where(User.username.like("b-owner-%"))
            )).all()
            b_id = rows[0][1]
            t1 = (await s.execute(select(Tenant.id).where(Tenant.slug.like("alpha-%")))).scalar_one()
            return b_id, t1

    b_user_id, a_tenant_id = asyncio.run(_ids())

    async def _go():
        async with db_session() as s:
            return await AuthService(s).create_token({
                "id": b_user_id, "username": "b-owner", "is_admin": False,
                "role": "admin", "tenant_id": a_tenant_id, "tenant_role": "owner",
                "is_platform_admin": False,
            })

    token = asyncio.run(_go())
    resp = db_client.get("/api/v1/members",
                         headers={"Authorization": f"Bearer {token.access_token}"})
    assert resp.status_code == 401


# ---------------- T12/F-01：撤销平台超管后存量 token 立即失去 platform_scope ----------------


def test_revoked_platform_admin_token_immediately_loses_platform_scope(
        db_client, db_engine, db_session):
    """F-01：撤销平台超管后，同一存量 token（不重签）立即失去平台态——双源一致钉

    中间件 platform_scope 判定与 deps 平台守卫共用 load_auth_identity 的 DB 快照：
    撤销后 (1) require_platform_admin 端点 403；(2) 隔离作用域降级为 DB 行租户的
    tenant_scope，跨租户数据不可见。撤销前同一 token 跨租户可见（在位对照，不误伤）。
    """

    async def _seed():
        async with db_session() as s:
            # T5 后平台超管挂 platform 租户（users.tenant_id NOT NULL）
            platform = Tenant(slug="platform-f01", name="平台租户")
            s.add(platform)
            await s.flush()
            s.add(User(username="f01-root", email="f01-root@x.local", password_hash="x",
                       role="admin", tenant_id=platform.id, tenant_role=None,
                       is_platform_admin=True))
            await s.commit()
            root = (await s.execute(
                select(User).where(User.username == "f01-root"))).scalar_one()
            token = await AuthService(s).create_token({
                "id": root.id, "username": "f01-root", "is_admin": True, "role": "admin",
                "tenant_id": None, "tenant_role": None, "is_platform_admin": True,
            })
            return token, root.id

    token, root_id = asyncio.run(_seed())
    auth = {"Authorization": f"Bearer {token.access_token}"}

    # 在位对照：撤销前（claim 与 DB 一致）平台态跨租户可见
    before = db_client.get("/api/v1/spiders/registry", headers=auth)
    assert before.status_code == 200
    assert "b-def-" in before.text

    # 撤销平台超管（DB 已降权；token 不重签——存量 TTL 内立即复验）
    async def _revoke():
        async with db_session() as s:
            await s.execute(
                update(User).where(User.id == root_id).values(is_platform_admin=False))
            await s.commit()

    asyncio.run(_revoke())

    # 双源一致：守卫层 403 + 隔离层降级租户态（跨租户不可见），同一 token
    guarded = db_client.get("/api/v1/admin/tenants", headers=auth)
    assert guarded.status_code == 403
    scoped = db_client.get("/api/v1/spiders/registry", headers=auth)
    assert scoped.status_code == 200
    assert "b-def-" not in scoped.text
