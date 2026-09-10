"""S5-1/5-2 企业注册 + 到期降级验证（工单 42/43 后端）

Seam（工单预确认）：/public/tenant/signup 端点 + expire_overdue_tenants + 登录拒绝。
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from backend.services.auth_service import AuthService
from backend.services.tenant_expiry_service import (
    AUTH_TENANT_EXPIRED,
    TENANT_EXPIRED_MESSAGE,
    expire_overdue_tenants,
)
from backend.services.tenant_signup_service import SIGNUP_INCOMPLETE_CODE, SIGNUP_INCOMPLETE_MESSAGE
from backend.utils.auth import get_password_hash
from platform_core.models.llm_token_usage import LlmTokenUsage
from platform_core.models.spider_result import SpiderResult
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

_MEMBER_PASSWORD = "SuperSecret1!"
_CREDENTIAL_MESSAGE = "用户名或密码错误"


@pytest.fixture(autouse=True)
def _no_signup_rate_limit(monkeypatch):
    """B1 限流与业务测试解耦：同 IP 连续 signup 用例会打满 5 次/15 分钟窗口（fail-closed 429）；
    限流语义由 test_b1_rate_limiter.py 专项覆盖。"""
    monkeypatch.setattr(
        "backend.app.api.v1.tenant_signup.enforce_request_limit",
        AsyncMock(return_value=None),
    )


def test_signup_creates_tenant_and_owner(db_client, db_engine, db_session):
    resp = db_client.post(
        "/api/v1/public/tenant/signup",
        json={"company": "Acme Corp", "admin_email": "boss@acme.com",
              "admin_password": "SuperSecret1!"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tenant"]["slug"] == "acme-corp"
    assert data["owner"]["tenant_role"] == "owner" if data["owner"].get("tenant_role") else True
    # owner 已可登录（最短路径）
    login = db_client.post("/api/v1/auth/login",
                           json={"username": data["owner"]["username"],
                                 "password": "SuperSecret1!"})
    assert login.status_code == 200


def _tenant_count(db_session) -> int:
    import asyncio

    async def _go() -> int:
        async with db_session() as s:
            return int((await s.execute(select(func.count()).select_from(Tenant))).scalar_one())

    return asyncio.run(_go())


def _tenant_name(db_session, slug: str) -> str | None:
    import asyncio

    async def _go() -> str | None:
        async with db_session() as s:
            return (await s.execute(select(Tenant.name).where(Tenant.slug == slug))).scalar_one_or_none()

    return asyncio.run(_go())


def _assert_no_tenant_leak(body: dict, *needles: str) -> None:
    blob = str(body)
    assert body.get("code") == SIGNUP_INCOMPLETE_CODE
    assert body.get("message") == SIGNUP_INCOMPLETE_MESSAGE
    for needle in needles:
        assert needle not in blob
    assert "已注册" not in blob
    assert "加入企业" not in blob


def test_signup_duplicate_email_rejected(db_client, db_engine, db_session):
    """GWT-04.2 / 04.4：占用邮箱失败不落新企业、不泄露其它企业是否存在。"""
    first = db_client.post("/api/v1/public/tenant/signup",
                           json={"company": "Acme Corp", "admin_email": "dup@x.com",
                                 "admin_password": "LongEnough1!"})
    assert first.status_code == 200
    before = _tenant_count(db_session)
    second = db_client.post("/api/v1/public/tenant/signup",
                            json={"company": "Hijack Co", "admin_email": "dup@x.com",
                                  "admin_password": "LongEnough1!"})
    assert second.status_code == 422
    _assert_no_tenant_leak(second.json(), "Acme Corp", "Hijack Co", "dup@x.com", "acme-corp")
    assert _tenant_count(db_session) == before
    assert _tenant_name(db_session, "acme-corp") == "Acme Corp"
    hijack_login = db_client.post("/api/v1/auth/login",
                                  json={"username": "dup", "password": "LongEnough1!"})
    assert hijack_login.status_code == 200  # 原企业仍可登录；没有第二家


def test_signup_weak_password_rejected(db_client, db_engine, db_session):
    """GWT-04.2：校验失败不创建可登录企业。"""
    before = _tenant_count(db_session)
    resp = db_client.post("/api/v1/public/tenant/signup",
                          json={"company": "WeakCo", "admin_email": "weakowner@x.com",
                                "admin_password": "short"})
    assert resp.status_code == 422
    assert _tenant_count(db_session) == before
    login = db_client.post("/api/v1/auth/login",
                           json={"username": "weakowner", "password": "not-created"})
    assert login.status_code == 401


def test_signup_readonly_member_cannot_convert_other_tenant(db_client, db_engine, db_session):
    """GWT-04.4：已有企业只读成员提交注册，不得改写他人企业，失败不泄露。"""
    import asyncio

    async def _seed() -> tuple[str, str]:
        async with db_session() as s:
            tenant = Tenant(slug="victim-co", name="Victim Co", status="active")
            s.add(tenant)
            await s.flush()
            s.add(User(
                username="victim-owner", email="owner@victim.test", password_hash="x",
                role="admin", tenant_id=tenant.id, tenant_role="owner",
                is_active=True, is_platform_admin=False,
            ))
            viewer = User(
                username="victim-viewer", email="viewer@victim.test", password_hash="x",
                role="viewer", tenant_id=tenant.id, tenant_role="viewer",
                is_active=True, is_platform_admin=False,
            )
            s.add(viewer)
            await s.commit()
            loaded = (await s.execute(select(User).where(User.username == "victim-viewer"))).scalar_one()
            token = await AuthService(s).create_token({
                "id": loaded.id, "username": loaded.username, "is_admin": False,
                "role": "viewer", "tenant_id": tenant.id, "tenant_role": "viewer",
                "is_platform_admin": False,
            })
            return token.access_token, tenant.slug

    token, slug = asyncio.run(_seed())
    before = _tenant_count(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    resp = db_client.post(
        "/api/v1/public/tenant/signup",
        headers=headers,
        json={"company": "Hijack Co", "admin_email": "new-boss@hijack.test",
              "admin_password": "SuperSecret1!"},
    )
    assert resp.status_code == 422
    _assert_no_tenant_leak(
        resp.json(), "Victim Co", "Hijack Co", "victim-co",
        "viewer@victim.test", "new-boss@hijack.test",
    )
    assert _tenant_count(db_session) == before
    assert _tenant_name(db_session, slug) == "Victim Co"
    assert _tenant_name(db_session, "hijack-co") is None
    stolen = db_client.post("/api/v1/auth/login",
                            json={"username": "new-boss", "password": "SuperSecret1!"})
    assert stolen.status_code == 401


def _assert_tenant_expired_response(resp) -> None:
    """GWT-08.1：到期/停用拒绝 ≠ 密码错误；不颁发可用会话。"""
    assert resp.status_code == 401, resp.text
    body = resp.json()
    assert body["code"] == AUTH_TENANT_EXPIRED
    assert body["message"] == TENANT_EXPIRED_MESSAGE
    assert body["message"] != _CREDENTIAL_MESSAGE
    assert "用户名或密码" not in body["message"]
    data = body.get("data")
    if isinstance(data, dict):
        assert not data.get("access_token")
    else:
        assert not data


async def _seed_member(
    db_session,
    *,
    slug: str,
    username: str,
    status: str = "active",
    expires_at: datetime | None = None,
    email: str | None = None,
) -> int:
    async with db_session() as s:
        tenant = Tenant(slug=slug, name=slug, status=status, expires_at=expires_at)
        s.add(tenant)
        await s.flush()
        tid = int(tenant.id)
        s.add(User(
            username=username,
            email=email or f"{username}@x.com",
            password_hash=get_password_hash(_MEMBER_PASSWORD),
            role="admin",
            tenant_id=tid,
            tenant_role="owner",
            is_active=True,
            is_platform_admin=False,
        ))
        await s.commit()
        return tid


@pytest.mark.asyncio
async def test_expired_tenant_login_rejected(db_client, db_engine, db_session):
    """GWT-08.1 / 08.3：到期成员登录失败且文案 ≠ 密码错误；另一有效企业不受影响。"""
    await _seed_member(
        db_session, slug="expired-co", username="exowner",
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1),
    )
    await _seed_member(
        db_session, slug="alive-co", username="aliveowner",
        email="alive@x.com",
    )

    async def _expire():
        async with db_session() as s:
            count = await expire_overdue_tenants(s)
            await s.commit()
            return count

    assert await _expire() == 1

    async def _status():
        async with db_session() as s:
            return (await s.execute(
                select(Tenant.status).where(Tenant.slug == "expired-co")
            )).scalar_one()

    assert await _status() == "expired"

    expired_login = db_client.post(
        "/api/v1/auth/login",
        json={"username": "exowner", "password": _MEMBER_PASSWORD},
    )
    _assert_tenant_expired_response(expired_login)

    wrong = db_client.post(
        "/api/v1/auth/login",
        json={"username": "exowner", "password": "not-the-password"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["code"] == "AUTH_FAILED"
    assert wrong.json()["message"] == _CREDENTIAL_MESSAGE
    assert wrong.json()["message"] != TENANT_EXPIRED_MESSAGE

    alive = db_client.post(
        "/api/v1/auth/login",
        json={"username": "aliveowner", "password": _MEMBER_PASSWORD},
    )
    assert alive.status_code == 200, alive.text
    assert alive.json()["data"]["access_token"]


def test_disabled_tenant_login_rejected(db_client, db_engine, db_session):
    """GWT-08.1：停用企业成员登录失败，文案与到期同一句，不是密码错误。"""
    import asyncio

    asyncio.run(_seed_member(
        db_session, slug="disabled-co", username="disowner", status="disabled",
    ))
    resp = db_client.post(
        "/api/v1/auth/login",
        json={"username": "disowner", "password": _MEMBER_PASSWORD},
    )
    _assert_tenant_expired_response(resp)


def test_preissued_session_writes_refused_after_expiry(db_client, db_engine, db_session):
    """GWT-08.2：到期前已颁发会话后续任务/模型写拒绝；不产生新任务、不消耗新 token。"""
    import asyncio

    tid = asyncio.run(_seed_member(
        db_session, slug="held-sess", username="held-owner",
    ))
    login = db_client.post(
        "/api/v1/auth/login",
        json={"username": "held-owner", "password": _MEMBER_PASSWORD},
    )
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    async def _expire() -> None:
        async with db_session() as s:
            tenant = (await s.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
            tenant.status = "expired"
            await s.commit()

    asyncio.run(_expire())

    async def _counts() -> tuple[int, int]:
        async with db_session() as s:
            tasks = int((await s.execute(
                select(func.count()).select_from(SpiderTask).where(SpiderTask.tenant_id == tid)
            )).scalar_one())
            tokens = int((await s.execute(
                select(func.count()).select_from(LlmTokenUsage).where(
                    LlmTokenUsage.tenant_id == tid
                )
            )).scalar_one())
            return tasks, tokens

    before = asyncio.run(_counts())
    run = db_client.post(
        "/api/v1/spiders/run",
        json={"spider_name": "example", "params": '{"urls": ["https://httpbin.org/get"]}'},
        headers=headers,
    )
    _assert_tenant_expired_response(run)
    plan = db_client.post(
        "/api/v1/ai/plans",
        json={"target_url": "https://example.com"},
        headers=headers,
    )
    _assert_tenant_expired_response(plan)
    assert asyncio.run(_counts()) == before


def test_platform_placeholder_marketplace_not_in_tenant_results(
    db_client, db_engine, db_session,
):
    """GWT-08.4：平台占位企业 marketplace 结果不出现在租户「我的结果」。"""
    import asyncio

    async def _seed() -> None:
        async with db_session() as s:
            platform = Tenant(slug="platform", name="平台租户", status="active")
            tenant = Tenant(slug="see-mine", name="SeeMine", status="active")
            s.add_all([platform, tenant])
            await s.flush()
            plat_id, tid = int(platform.id), int(tenant.id)
            plat_task = SpiderTask(
                spider_name="skill_harvester", tenant_id=plat_id,
                status="completed", params="{}",
            )
            mine_task = SpiderTask(
                spider_name="example", tenant_id=tid,
                status="completed", params="{}",
            )
            s.add_all([plat_task, mine_task])
            await s.flush()
            s.add_all([
                SpiderResult(
                    task_id=plat_task.id, spider_name="skill_harvester",
                    title="plat-mkt", source="marketplace",
                    url="https://market.example/item", tenant_id=plat_id,
                ),
                SpiderResult(
                    task_id=mine_task.id, spider_name="example",
                    title="mine-row", source="crawl",
                    url="https://mine.example/item", tenant_id=tid,
                ),
            ])
            s.add(User(
                username="see-owner", email="see@x.com",
                password_hash=get_password_hash(_MEMBER_PASSWORD),
                role="admin", tenant_id=tid, tenant_role="owner",
                is_active=True, is_platform_admin=False,
            ))
            await s.commit()

    asyncio.run(_seed())
    login = db_client.post(
        "/api/v1/auth/login",
        json={"username": "see-owner", "password": _MEMBER_PASSWORD},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    resp = db_client.get("/api/v1/spiders/results", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    titles = {i["title"] for i in items}
    assert "plat-mkt" not in titles
    assert "mine-row" in titles
    assert "marketplace" not in {i.get("source") for i in items}


def test_platform_ops_tenant_list(db_client, admin_client, db_engine, db_session):
    """平台运营台：固定 admin（非平台超管）404 同形；平台超管 token 可见租户列表"""
    # 默认测试身份（无 Bearer→固定 admin 快照，is_platform_admin=False）应被拒
    denied = db_client.get("/api/v1/admin/tenants")
    assert denied.status_code == 404
    assert denied.json()["code"] == "HTTP_404"

    import asyncio

    from backend.services.auth_service import AuthService
    from platform_core.models.user import User

    async def _go():
        async with db_session() as s:
            # T5 后平台超管挂 platform 租户（users.tenant_id NOT NULL）
            platform = Tenant(slug="platform", name="平台租户")
            s.add(platform)
            await s.flush()
            s.add(User(username="rootop", email="rootop@x.com", password_hash="x",
                       role="admin", tenant_id=platform.id, tenant_role=None,
                       is_platform_admin=True))
            await s.commit()
            root = (await s.execute(select(User).where(User.username == "rootop"))).scalar_one()
            return await AuthService(s).create_token({
                "id": root.id, "username": "rootop", "is_admin": True, "role": "admin",
                "tenant_id": None, "tenant_role": None, "is_platform_admin": True,
            })

    token = asyncio.run(_go())
    allowed = db_client.get("/api/v1/admin/tenants",
                            headers={"Authorization": f"Bearer {token.access_token}"})
    assert allowed.status_code == 200
    assert isinstance(allowed.json()["data"], list)
