"""S1-5 R13 越权测试套件（工单 35）：A 租户访问 B 租户资源全 403/404

Seam（工单预确认）：db_client（真实 JWT → 中间件 → tenant_scope → 行级隔离全链路）。
覆盖资源类：spiders/tasks / spiders/definitions / spiders/templates / ai / llm/providers
（skills 为平台级豁免——全租户共享只读，不在越权面）。
"""
import asyncio

import pytest
from sqlalchemy import select

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
            s.add(User(username="root", email="root@x.local", password_hash="x",
                       role="admin", tenant_id=None, tenant_role=None,
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
