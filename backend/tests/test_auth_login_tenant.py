"""T5 登录租户消歧（决策 A）：跨租户同名 + 密码消歧 + 软删拦截 + register 挂 default

Seam：/api/v1/auth/login、/api/v1/auth/register 端点（db_client 真链路：
get_by_username 返回多行候选 → auth_service 逐行验密码，唯一命中胜出）。

体检发现 1 回归：同名多行不再 MultipleResultsFound 500。
关键前提钉住：登录请求无 token → 中间件不设作用域 → TenantMixin 自动过滤
不动——若未来给登录加租户作用域，多租户同名用例将在此处失败（口径声明见
UserRepository.get_by_username 的 R13 注释）。
"""
import asyncio

import pytest
from sqlalchemy import select

from platform_core.models.tenant import Tenant
from platform_core.models.user import User
from platform_core.queues import LOGIN_FAIL_PREFIX, REGISTER_ATTEMPT_PREFIX
from platform_core.redis_async import get_async_redis
from backend.utils.auth import get_password_hash

STATE: dict = {}


async def _seed(db_session) -> None:
    async with db_session() as s:
        default = Tenant(slug="default", name="默认租户")
        ta = Tenant(slug="alpha-t5", name="A")
        tb = Tenant(slug="beta-t5", name="B")
        s.add_all([default, ta, tb])
        await s.flush()
        s.add_all([
            # 跨租户同名、密码不同：密码消歧可判定
            User(username="dup-user", email="dup-a@x.local",
                 password_hash=get_password_hash("alpha-pass-123"),
                 role="viewer", tenant_id=ta.id, tenant_role="viewer"),
            User(username="dup-user", email="dup-b@x.local",
                 password_hash=get_password_hash("beta-pass-123"),
                 role="viewer", tenant_id=tb.id, tenant_role="viewer"),
            # 跨租户同名、密码相同：凭据无法消歧 → 必须 401
            User(username="twin-user", email="twin-a@x.local",
                 password_hash=get_password_hash("twin-pass-123"),
                 role="viewer", tenant_id=ta.id, tenant_role="viewer"),
            User(username="twin-user", email="twin-b@x.local",
                 password_hash=get_password_hash("twin-pass-123"),
                 role="viewer", tenant_id=tb.id, tenant_role="viewer"),
        ])
        await s.commit()
        # 软删用户（密码正确）：deleted_at 过滤 → 401（直接 UPDATE 路径，不依赖 is_active）
        gone = User(username="gone-user", email="gone@x.local",
                    password_hash=get_password_hash("gone-pass-123"),
                    role="viewer", tenant_id=ta.id, tenant_role="viewer",
                    is_active=True)
        s.add(gone)
        await s.flush()
        from sqlalchemy import func, update as sa_update

        await s.execute(sa_update(User).where(User.id == gone.id)
                        .values(deleted_at=func.now()))
        await s.commit()
        STATE["default_id"] = default.id
        STATE["b_id"] = tb.id


@pytest.fixture(autouse=True)
def seeded(db_session):
    asyncio.run(_seed(db_session))
    yield


# 本文件 db_client 走真链路（登录/注册限流计数落本机 Redis，5 次/900s 跨轮次存活），
# 固定用户名会被 401 消歧用例喂爆、testclient IP 会被全仓注册用例累计 → 200 变 429。逐用例清零。
_LOGIN_FAIL_USERS = ("dup-user", "twin-user", "gone-user", "pub-reg-user")


@pytest.fixture(autouse=True)
def clear_login_fail_counters():
    async def _clear() -> None:
        redis = get_async_redis()
        keys = [f"{LOGIN_FAIL_PREFIX}{u}" for u in _LOGIN_FAIL_USERS]
        keys.append(f"{REGISTER_ATTEMPT_PREFIX}testclient")
        await redis.delete(*keys)

    asyncio.run(_clear())
    yield


def test_dup_username_unique_password_match_wins(db_client):
    """同名双租户、密码不同：唯一命中者胜出，返回其真实 tenant_id"""
    resp = db_client.post("/api/v1/auth/login",
                          json={"username": "dup-user", "password": "beta-pass-123"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["tenant_id"] == STATE["b_id"]
    assert data["access_token"]


def test_dup_username_wrong_password_401_not_500(db_client):
    """同名双租户、密码皆不中：401（体检发现 1——旧行为 MultipleResultsFound 500）"""
    resp = db_client.post("/api/v1/auth/login",
                          json={"username": "dup-user", "password": "wrong-pass-9"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_FAILED"
    # 错误信息不泄露候选行数（多行/单行/零行同文案）
    assert "2" not in resp.json().get("message", "")


def test_dup_username_same_password_unresolvable_401(db_client):
    """同名双租户、密码相同：凭据无法消歧 → 401（多中即拒绝）"""
    resp = db_client.post("/api/v1/auth/login",
                          json={"username": "twin-user", "password": "twin-pass-123"})
    assert resp.status_code == 401


def test_soft_deleted_user_cannot_login(db_client):
    """软删用户（密码正确、deleted_at 置位）：401——登录路径过滤软删行"""
    resp = db_client.post("/api/v1/auth/login",
                          json={"username": "gone-user", "password": "gone-pass-123"})
    assert resp.status_code == 401


def test_login_accepts_reserved_tenant_slug_field(db_client):
    """LoginRequest 预留 tenant_slug（可选、暂不消费）：携带不炸、语义不变"""
    resp = db_client.post("/api/v1/auth/login", json={
        "username": "dup-user", "password": "alpha-pass-123", "tenant_slug": "alpha-t5"})
    assert resp.status_code == 200
    # 缺省（现有前端形态）不受影响
    resp2 = db_client.post("/api/v1/auth/login",
                           json={"username": "dup-user", "password": "alpha-pass-123"})
    assert resp2.status_code == 200


def test_register_creates_default_tenant_user(db_client, db_session):
    """公开注册（决策 B）：新用户挂 default 租户 + tenant_role=viewer，绝不产 NULL 行"""
    resp = db_client.post("/api/v1/auth/register", json={
        "username": "pub-reg-user", "email": "pub@x.local", "password": "PubPass123!"})
    assert resp.status_code == 200, resp.text

    async def _row():
        async with db_session() as s:
            return (await s.execute(
                select(User).where(User.username == "pub-reg-user"))).scalar_one()

    user = asyncio.run(_row())
    assert user.tenant_id == STATE["default_id"]
    assert user.tenant_role == "viewer"
    assert user.is_platform_admin is False

    # 注册后可登录（default 租户用户正常链路）
    login = db_client.post("/api/v1/auth/login", json={
        "username": "pub-reg-user", "password": "PubPass123!"})
    assert login.status_code == 200
    assert login.json()["data"]["tenant_id"] == STATE["default_id"]
