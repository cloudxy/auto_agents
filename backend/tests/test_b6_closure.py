"""B6 尾巴收口（工单 91）：用量成员维度 / 成员审计租户视角 / webhook 状态

Seam：租户视角端点走真实 JWT（owner）上下文（模式同 test_saas_members.py）；
期望值来自独立事实源（种子字面量）。
"""
import asyncio

import pytest

from backend.services.auth_service import AuthService
from platform_core.models.operation_log import OperationLog
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

STATE: dict = {}


async def _seed(db_session) -> None:
    async with db_session() as s:
        t = Tenant(slug=f"b6-{id(db_session)}", name="B6")
        s.add(t)
        await s.flush()
        owner = User(username="b6-owner", email="b6o@x.local", password_hash="x",
                     role="admin", tenant_id=t.id, tenant_role="owner")
        outsider = User(username="b6-other", email="b6t@x.local", password_hash="x",
                        role="admin", tenant_id=t.id + 100, tenant_role="owner")
        s.add_all([owner, outsider])
        await s.commit()
        await s.flush()
        s.add(OperationLog(actor_id=owner.id, actor_name="b6-owner",
                           action="member.update", target="user#9"))
        s.add(OperationLog(actor_id=outsider.id, actor_name="b6-other",
                           action="member.update", target="user#8"))
        await s.commit()

        svc = AuthService(s)
        token = await svc.create_token({
            "id": owner.id, "username": owner.username, "is_admin": True,
            "role": "admin", "tenant_id": t.id, "tenant_role": "owner",
            "is_platform_admin": False,
        })
        STATE["token"] = token.access_token
        STATE["tenant"] = t.id
        STATE["owner_id"] = owner.id


@pytest.fixture(autouse=True)
def seeded(db_session):
    asyncio.run(_seed(db_session))
    yield


def _auth() -> dict:
    return {"Authorization": f"Bearer {STATE['token']}"}


def test_usage_by_member_returns_created_by_aggregation(db_client, db_session):
    """成员分摊：spider_tasks 按 created_by 聚合（NULL 归系统）"""
    from platform_core.models.spider_task import SpiderTask

    async def _seed_tasks():
        async with db_session() as s:
            s.add(SpiderTask(tenant_id=STATE["tenant"], spider_name="a",
                             status="completed", params="{}", created_by="b6-owner"))
            s.add(SpiderTask(tenant_id=STATE["tenant"], spider_name="b",
                             status="completed", params="{}", created_by="b6-owner"))
            s.add(SpiderTask(tenant_id=STATE["tenant"], spider_name="c",
                             status="pending", params="{}", created_by=None))
            await s.commit()

    asyncio.run(_seed_tasks())

    resp = db_client.get("/api/v1/tenants/me/usage/by-member", headers=_auth())
    assert resp.status_code == 200
    rows = {r["member"]: r["tasks"] for r in resp.json()["data"]}
    assert rows["b6-owner"] == 2
    assert rows["（系统/调度）"] == 1


def test_member_audit_scoped_to_tenant(db_client):
    """成员审计·租户视角：仅本租户成员的操作留痕可见"""
    resp = db_client.get("/api/v1/members/audit?limit=50", headers=_auth())
    assert resp.status_code == 200
    names = [r["actor_name"] for r in resp.json()["data"]]
    assert "b6-owner" in names
    assert "b6-other" not in names  # 跨租户不可见


def test_webhook_status_never_leaks_secret_value(db_client):
    """webhook 状态：只回显配置态布尔，无任何密钥值（admin 快照即可达）"""
    resp = db_client.get("/api/v1/admin/webhook-status")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert set(body) == {
        "secret_configured", "notify_webhook_url_configured",
        "dingtalk_configured", "wechat_work_configured", "env_override_active",
    }
    assert all(isinstance(v, bool) for v in body.values())
