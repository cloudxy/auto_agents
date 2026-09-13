"""pytest 全局 fixture - FastAPI TestClient 与环境准备

约定：
- 测试统一使用 local 环境配置（config/local/）
- 不连接真实 MySQL/Redis（涉及 DB 的测试用 mock 或跳过）
- 运行方式：uv run pytest -x -q backend/tests
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator, Callable, Iterator

import pytest

if TYPE_CHECKING:
    from contextlib import AsyncContextManager

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

# 确保仓库根目录在 sys.path（pytest 从任意层级调用时均可导入顶层包）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 确保 tests 目录在 sys.path（共享桩模块 stubs.py 的显式导入依赖）
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

# 固定测试环境为 local（必须在导入 config 之前设置）
os.environ.setdefault("APP_ENV", "local")
# T1：测试态 bcrypt 因子降到 4，避免登录链被 12 轮拖进分钟级
os.environ.setdefault("BCRYPT_ROUNDS", "4")


# ── get_async_db 全局兜底 mock（CI 无 .env，防意外连真库）──
from unittest.mock import AsyncMock, MagicMock as _MM

from fastapi import Request as _FastAPIRequest  # noqa: N812 模块级导入：本文件启用延迟注解（from __future__ import annotations），嵌套函数内的局部 import 无法被 FastAPI 的注解解析看到
from platform_core.db import get_async_db as _gadb


async def _mock_async_db():
    mock_session = _MM()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.execute = AsyncMock(return_value=_MM(
        scalar_one_or_none=_MM(return_value=None),
        scalars=_MM(return_value=_MM(all=_MM(return_value=[]))),
        first=_MM(return_value=None),
    ))
    yield mock_session


# ---------------------------------------------------------------------------
# 鉴权 override（T10 收紧）：模块级单一实现，app fixture 与特权 fixtures 共用
#
# 口径：
# - 默认（role=None，client fixture）：无凭据请求 → 401，与生产 get_current_user
#   完全同口径；「端点忘挂 RBAC 守卫」不再被全局兜底 admin 掩盖（测试侧即红）。
# - 特权身份经 opt-in fixture 显式声明：admin_client / operator_client /
#   viewer_client（无凭据请求以对应角色快照通过）。
# - 带真实 Bearer 时一律走真链路（JWT→DB 快照，S1/S2 越权与成员用例依赖）。
# - RBAC 守卫自身的 401/403 分支由 test_rbac_audit.py 直接单测。
# ---------------------------------------------------------------------------


async def _current_user_override(request, credentials, session, default_role: str | None):
    """无凭据按 default_role 分派（None=401）；带 Bearer 走真链路"""
    from backend.app.api.deps import CurrentUser, effective_role
    from backend.services.user_service import load_auth_identity
    from backend.utils.auth import decode_access_token as _decode
    from platform_core.exceptions import AuthenticationException

    # 带真实 Bearer 时走真链路（S1/S2 越权与成员用例依赖 JWT→中间件→快照全链）。
    # F-01 同口径：中间件平台态复核已挂载的快照（request.state.auth_identity）
    # 优先消费；否则经 load_auth_identity 加载（单一事实源与生产 deps 一致）。
    # 有 user_id 但查无此人/停用 → 401；T5 后 session.get 受 tenant_scope 注入
    # 过滤，伪造租户 token 落此分支
    if credentials is not None and getattr(credentials, "credentials", ""):
        payload = _decode(credentials.credentials)
        if payload and payload.get("user_id"):
            identity = getattr(request.state, "auth_identity", None)
            if identity is None:
                identity = await load_auth_identity(session, payload["user_id"])
            if identity is None or not identity.is_active:
                raise AuthenticationException(message="用户不存在或已停用")
            from backend.services.tenant_expiry_service import assert_tenant_active

            await assert_tenant_active(
                session,
                identity.tenant_id,
                is_platform_admin=identity.is_platform_admin,
            )
            return CurrentUser(
                id=identity.id, username=identity.username, role=effective_role(identity),
                tenant_id=identity.tenant_id, tenant_role=identity.tenant_role,
                is_platform_admin=identity.is_platform_admin,
            )
    if default_role is None:
        raise AuthenticationException(message="未登录或缺少 Token")
    is_plat = default_role == "platform_admin"
    return CurrentUser(
        id=1,
        username=f"test-{default_role}",
        role="admin" if is_plat else default_role,
        is_platform_admin=is_plat,
        tenant_id=None if is_plat else (1 if default_role == "admin" else None),
        tenant_role=None if is_plat else ("owner" if default_role == "admin" else None),
    )


def _make_auth_override(role: str | None):
    """构造符合 FastAPI 依赖签名的鉴权 override（role=None 为匿名口径）

    request 注解须用模块级 _FastAPIRequest（延迟注解解析只查模块全局，见文件头）。
    """
    from fastapi import Depends

    from backend.app.api.deps import _bearer
    from platform_core.db import get_async_db as _get_async_db

    async def _override(
        request: _FastAPIRequest,
        credentials=Depends(_bearer),
        session=Depends(_get_async_db),
    ):
        return await _current_user_override(request, credentials, session, default_role=role)

    return _override


def _set_auth_override(app, role: str | None) -> None:
    from backend.app.api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_auth_override(role)


@pytest.fixture(scope="session")
def app():
    """FastAPI 应用实例（含异常处理器与全量路由；鉴权默认匿名口径，见上）"""
    from backend.app import create_app
    from backend.app.api.deps import get_current_user

    application = create_app()

    application.dependency_overrides[get_current_user] = _make_auth_override(None)
    application.dependency_overrides[_gadb] = _mock_async_db
    return application


@pytest.fixture(scope="session")
def client(app):
    """FastAPI TestClient（同步 HTTP 测试入口，匿名口径：无凭据 401）"""
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_auth_override(app):
    """每个测试前后将鉴权 override 归位为匿名口径——防特权 fixture / 前序测试
    残留（同 _reset_get_async_db 的加固模式）"""
    _set_auth_override(app, None)
    yield
    _set_auth_override(app, None)


@pytest.fixture
def admin_client(app, client, _reset_auth_override):
    """admin 特权 TestClient（租户 admin，非平台超管）"""
    _set_auth_override(app, "admin")
    yield client
    _set_auth_override(app, None)


@pytest.fixture
def platform_admin_client(app, client, _reset_auth_override):
    """平台超管 TestClient（require_platform_admin 放行）"""
    _set_auth_override(app, "platform_admin")
    yield client
    _set_auth_override(app, None)


@pytest.fixture
def operator_client(app, client, _reset_auth_override):
    """operator 特权 TestClient（require_login/require_operator 放行，admin 拒绝）"""
    _set_auth_override(app, "operator")
    yield client
    _set_auth_override(app, None)


@pytest.fixture
def viewer_client(app, client, _reset_auth_override):
    """viewer 特权 TestClient（仅 require_login 放行——403 越权断言用）"""
    _set_auth_override(app, "viewer")
    yield client
    _set_auth_override(app, None)


@pytest.fixture
def platform_admin_client(app, client, _reset_auth_override):
    """平台超管特权 TestClient（is_platform_admin=True；无凭据请求以超管快照通过）

    T-04：平台写面 require_platform_admin。admin_client 是租户公司管理员
    （role=admin 且 is_platform_admin=False）——GWT-06.3 拒绝身份，不是超管。
    带真实 Bearer 仍走 JWT→DB 快照真链路。
    """
    from fastapi import Depends

    from backend.app.api.deps import CurrentUser, _bearer, get_current_user
    from platform_core.db import get_async_db as _get_async_db

    async def _override(
        request: _FastAPIRequest,
        credentials=Depends(_bearer),
        session=Depends(_get_async_db),
    ):
        if credentials is not None and getattr(credentials, "credentials", ""):
            return await _current_user_override(
                request, credentials, session, default_role=None,
            )
        return CurrentUser(
            id=1, username="test-platform-admin", role="admin",
            is_platform_admin=True,
        )

    app.dependency_overrides[get_current_user] = _override
    yield client
    _set_auth_override(app, None)


def make_platform_admin_headers(db_session) -> dict:
    """平台超管 Bearer（真链路：platform 租户 + is_platform_admin 用户 + JWT）"""
    import asyncio

    from backend.services.auth_service import AuthService
    from platform_core.models.tenant import Tenant
    from platform_core.models.user import User
    from sqlalchemy import select

    async def _go():
        async with db_session() as s:
            platform = Tenant(slug="platform", name="平台租户")
            s.add(platform)
            await s.flush()
            s.add(User(
                username="t04-root", email="t04-root@x.com", password_hash="x",
                role="admin", tenant_id=platform.id, tenant_role=None,
                is_platform_admin=True, is_admin=True,
            ))
            await s.commit()
            root = (await s.execute(
                select(User).where(User.username == "t04-root"))).scalar_one()
            token = await AuthService(s).create_token({
                "id": root.id, "username": "t04-root", "is_admin": True, "role": "admin",
                "tenant_id": None, "tenant_role": None, "is_platform_admin": True,
            })
            return token.access_token

    return {"Authorization": f"Bearer {asyncio.run(_go())}"}


def make_tenant_owner_headers(db_session, *, slug: str = "co-a") -> tuple[dict, int]:
    """企业负责人 Bearer（role=admin, is_platform_admin=False）+ tenant_id"""
    import asyncio

    from backend.services.auth_service import AuthService
    from platform_core.models.tenant import Tenant
    from platform_core.models.user import User
    from sqlalchemy import select

    async def _go():
        async with db_session() as s:
            tenant = Tenant(slug=slug, name=f"公司-{slug}")
            s.add(tenant)
            await s.flush()
            tid = int(tenant.id)
            s.add(User(
                username=f"owner-{slug}", email=f"owner-{slug}@x.com", password_hash="x",
                role="admin", tenant_id=tid, tenant_role="owner",
                is_platform_admin=False, is_admin=True,
            ))
            await s.commit()
            owner = (await s.execute(
                select(User).where(User.username == f"owner-{slug}"))).scalar_one()
            token = await AuthService(s).create_token({
                "id": owner.id, "username": owner.username, "is_admin": True,
                "role": "admin", "tenant_id": tid, "tenant_role": "owner",
                "is_platform_admin": False,
            })
            return token.access_token, tid

    token, tid = asyncio.run(_go())
    return {"Authorization": f"Bearer {token}"}, tid


# ---------------------------------------------------------------------------
# DB fixture（E0.1a/1c 工单 01/03）：SQLite 会话与测试间隔离 + MySQL 保真通道
#
# 约束：
# - TestClient 每请求新建事件循环，引擎必须 NullPool（连接不跨循环复用），
#   与 platform_core/db.py 的 pytest 态处理同一口径；
# - SQLite 模式：每测试独立 tmp 文件库（非共享内存库）——隔离即"全新库"；
# - MySQL 保真模式（MYSQL_FIDELITY=1）：连真实 MySQL，每测试独立 schema
#   （会话级建删），凭据只走 MYSQL_FIDELITY_* 环境变量，不落任何 yml；
#   服务端不可达时报清晰错误（fail-fast），不静默回退 SQLite。
# ---------------------------------------------------------------------------

_MYSQL_FIDELITY_DB_PREFIX = "test_auto_agents"


def mysql_fidelity_enabled() -> bool:
    """MYSQL_FIDELITY 开关（"1"/"true"/"yes" 视为开启）"""
    return os.environ.get("MYSQL_FIDELITY", "").strip().lower() in ("1", "true", "yes")


def _mysql_fidelity_parts() -> tuple[str, str]:
    """返回 (server_url 无库名, 独立测试 schema 名)"""
    import uuid
    from urllib.parse import quote_plus

    host = os.environ.get("MYSQL_FIDELITY_HOST", "127.0.0.1")
    port = os.environ.get("MYSQL_FIDELITY_PORT", "3306")
    user = os.environ.get("MYSQL_FIDELITY_USER", "root")
    password = quote_plus(os.environ.get("MYSQL_FIDELITY_PASSWORD", ""))
    server_url = f"mysql+aiomysql://{user}:{password}@{host}:{port}/"
    schema = f"{_MYSQL_FIDELITY_DB_PREFIX}_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    return server_url, schema


async def _run_schema_ddl(server_url: str, statement: str) -> None:
    """在 server 层执行 CREATE/DROP DATABASE（独立短生命周期引擎）"""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(server_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text(statement))
    finally:
        await engine.dispose()


@pytest.fixture
def db_engine(tmp_path: Path) -> Iterator["AsyncEngine"]:
    """每测试独立的异步引擎：默认 SQLite 文件库；MYSQL_FIDELITY=1 时真实 MySQL 独立 schema"""
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    import platform_core.models  # noqa: F401 触发全模型注册到 Base.metadata
    from platform_core.models.base import Base

    mysql_schema: str | None = None
    if mysql_fidelity_enabled():
        server_url, mysql_schema = _mysql_fidelity_parts()
        asyncio.run(_run_schema_ddl(server_url, f"CREATE DATABASE `{mysql_schema}` CHARACTER SET utf8mb4"))
        url: str = f"{server_url}{mysql_schema}"
    else:
        url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"

    engine = create_async_engine(url, poolclass=NullPool)

    async def _create_all() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create_all())
    # ADR-0007 D4 / GWT-06.1：record_audit_standalone 读 DEFAULT。注入本测试引擎，
    # 禁止 init_all() 连真库，也禁止 API 钩子回写请求 session。_reset_db_manager
    # 在本 fixture 之前 purge，teardown 再 purge。
    import platform_core.db as _db

    manager = _db.get_manager()
    manager.async_engines["DEFAULT"] = engine
    yield engine
    if manager.async_engines.get("DEFAULT") is engine:
        manager.async_engines.pop("DEFAULT", None)
    asyncio.run(engine.dispose())
    if mysql_schema is not None:
        asyncio.run(_run_schema_ddl(server_url, f"DROP DATABASE `{mysql_schema}`"))


@pytest.fixture
def db_session(
    db_engine: "AsyncEngine",
) -> Callable[[], "AsyncContextManager[AsyncSession]"]:
    """AsyncSession 工厂（返回 asynccontextmanager）——会话在调用方事件循环内创建

    形态为工厂而非会话实例：TestClient 每请求独立事件循环，会话必须在使用方循环内创建。
    """
    from contextlib import asynccontextmanager

    from sqlalchemy.ext.asyncio import AsyncSession

    @asynccontextmanager
    async def _make_session() -> AsyncIterator["AsyncSession"]:
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            yield session

    return _make_session


@pytest.fixture(autouse=True)
def _reset_get_async_db(app):
    """每个测试前确保 get_async_db 指向全局兜底 mock——防前序测试的
    dependency_overrides 残留（如 test_ai_planner 直设 lambda 不清理）"""
    app.dependency_overrides[_gadb] = _mock_async_db
    yield
    # 测试后也重置（db_client teardown 之外的兜底）
    app.dependency_overrides[_gadb] = _mock_async_db


@pytest.fixture(autouse=True)
def _reset_db_manager():
    """每个测试前后清空 DBManager 全局单例的已初始化引擎（T10 测试卫生修复）

    根因（T7/T9 留档的 TestLlmChat 同批偶发 5 failed）：
    backend/services/ai_planner/llm_client.py::_resolve_llm_runtime_config 经
    get_manager().async_engines["DEFAULT"] 开独立短事务，**绕过** conftest 对
    get_async_db 的 override 直连真实 local MySQL。单跑/全量绿是因为 pytest
    进程内 DBManager 从未初始化 → KeyError → 降级 yml/env（LLM.ENABLED=false）。
    一旦批内任一代码触发惰性 init_all()（db.py 的 `if not self._ready` 三处），
    DEFAULT 引擎就绪 → 真库 llm_providers 激活行生效 → TestLlmChat 的
    「无激活供应商」全局假设断裂，且 llm_chat 会发起真实付费调用。

    修复口径：每测试结束即清空单例引擎缓存（pytest 态引擎为 NullPool，无
    连接驻留，直接清 dict 安全），使「引擎未初始化」的降级语义在测试间稳定。
    """
    import platform_core.db as _db

    def _purge() -> None:
        manager = getattr(_db, "_manager", None)
        if manager is not None:
            manager.async_engines.clear()
            manager.mysql.clear()
            manager.redis.clear()
            manager._ready = False  # noqa: SLF001 测试卫生收口，唯一写入口

    _purge()
    yield
    _purge()


@pytest.fixture(autouse=True)
def _power_market_enabled_for_tests():
    """公开/订阅测默认打开总开关；关闭路径在用例里 settings.set False（FR-U11）。"""
    from config import settings

    original = settings.get("POWER_MARKET.ENABLED")
    settings.set("POWER_MARKET.ENABLED", True)
    try:
        yield
    finally:
        settings.set("POWER_MARKET.ENABLED", original)


@pytest.fixture(autouse=True)
def _workers_online_unless_offline_node(request, monkeypatch):
    """入队闸默认报告工人在线；离线节点（GWT-18.2/18.4 / FR-U02.1）走真心跳扫描。"""
    nodeid = request.node.nodeid
    if "test_spider_worker_offline.py" in nodeid or "test_fr_u01_enqueue.py" in nodeid:
        return

    async def _online(_client) -> int:
        return 1

    monkeypatch.setattr(
        "backend.services.spider_worker_gate.count_online_workers",
        _online,
    )


def _purge_quota_count_keys() -> None:
    """DEL quota:count:* / login_fail:* via URL 直连（禁止 redis_client→init_all 拉真 MySQL）。

    login_fail:*（既有缺口，三票回报）：本机 Redis 限流计数跨测试存活，曾把
    test_gwt_15_4 的 fail-a/locked-a 喂爆 429 假红——与 quota:count:* 同口径清理。
    """
    import redis as redis_sync

    from config import settings
    from platform_core.queues import LOGIN_FAIL_PREFIX, QUOTA_COUNT_PREFIX

    url = str(settings.get("REDIS.DEFAULT.URL") or "")
    if not url:
        return
    client = redis_sync.from_url(url, decode_responses=True, socket_connect_timeout=0.5)
    try:
        for prefix in (QUOTA_COUNT_PREFIX, LOGIN_FAIL_PREFIX):
            keys = list(client.scan_iter(match=f"{prefix}*", count=200))
            if keys:
                client.delete(*keys)
    finally:
        client.close()


@pytest.fixture(autouse=True)
def _clear_quota_count_cache():
    """每测前清配额 COUNT 缓存，避免 60s TTL 污染 SQLite 新库的 tenant 计数。"""
    try:
        _purge_quota_count_keys()
    except Exception:  # noqa: BLE001 不可达则 _cached_count 回源 DB
        pass
    yield


@pytest.fixture
def db_client(
    app: "FastAPI", client: "TestClient", db_session: "Callable[[], AsyncContextManager[AsyncSession]]"
) -> Iterator["TestClient"]:
    """DB 接线版 TestClient：get_async_db 覆写为本测试引擎的会话工厂（测后还原）

    会话构造统一走 db_session（单一构造点）；端点与测试断言共享同一引擎同一库文件。
    F-01：中间件平台态 DB 复核的会话源（app.state.identity_session_factory）一并
    接线到本测试引擎（生产默认走 DBManager，测试态引擎被逐测试清空、不可直连）。
    """
    from contextlib import asynccontextmanager

    from platform_core.db import get_async_db

    async def _override_get_async_db() -> AsyncIterator["AsyncSession"]:
        async with db_session() as session:
            yield session

    @asynccontextmanager
    async def _middleware_identity_session() -> AsyncIterator["AsyncSession"]:
        async with db_session() as session:
            yield session

    app.dependency_overrides[get_async_db] = _override_get_async_db
    app.state.identity_session_factory = _middleware_identity_session
    yield client
    # 恢复全局兜底 mock（而非 pop——防止后续 client 测试意外连真库）；
    # 复核会话源还原生产默认（删除覆写）
    app.dependency_overrides[get_async_db] = _mock_async_db
    del app.state.identity_session_factory
