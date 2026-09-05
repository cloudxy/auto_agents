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


# ── get_async_db 全局兜底 mock（CI 无 .env，防意外连真库）──
from unittest.mock import AsyncMock, MagicMock as _MM

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


@pytest.fixture(scope="session")
def app():
    """FastAPI 应用实例（含异常处理器与全量路由）

    测试环境全局 override 鉴权依赖：端点测试默认以 admin 身份通过，
    RBAC 守卫自身的 401/403 分支由 test_rbac_audit.py 直接单测。
    """
    from fastapi import Depends

    from backend.app import create_app
    from backend.app.api.deps import CurrentUser, _bearer, get_current_user
    from backend.utils.auth import decode_access_token as _decode
    from platform_core.db import get_async_db as _get_async_db
    from platform_core.models.user import User as _User

    application = create_app()

    async def _override_current_user(
        credentials=Depends(_bearer),
        session=Depends(_get_async_db),
    ):
        # 带真实 Bearer 时走真链路（S1/S2 越权与成员用例依赖 JWT→中间件→快照全链）；
        # 无凭据时保持既有契约：固定 admin 快照（存量 600+ 测试零改动）。
        # 有 user_id 但查无此人/停用 → 401（与生产 get_current_user 同口径；
        # T5 后 session.get 受 tenant_scope 注入过滤，伪造租户 token 落此分支）
        from backend.app.api.deps import effective_role
        from platform_core.exceptions import AuthenticationException

        if credentials is not None and getattr(credentials, "credentials", ""):
            payload = _decode(credentials.credentials)
            if payload and payload.get("user_id"):
                user = await session.get(_User, payload["user_id"])
                if not user or not user.is_active:
                    raise AuthenticationException(message="用户不存在或已停用")
                return CurrentUser(
                    id=user.id, username=user.username, role=effective_role(user),
                    tenant_id=user.tenant_id, tenant_role=user.tenant_role,
                    is_platform_admin=bool(user.is_platform_admin),
                )
        return CurrentUser(id=1, username="test-admin", role="admin")

    application.dependency_overrides[get_current_user] = _override_current_user

    application.dependency_overrides[_gadb] = _mock_async_db
    return application


@pytest.fixture(scope="session")
def client(app):
    """FastAPI TestClient（同步 HTTP 测试入口）"""
    from fastapi.testclient import TestClient

    return TestClient(app)


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
    yield engine
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

@pytest.fixture
def db_client(
    app: "FastAPI", client: "TestClient", db_session: "Callable[[], AsyncContextManager[AsyncSession]]"
) -> Iterator["TestClient"]:
    """DB 接线版 TestClient：get_async_db 覆写为本测试引擎的会话工厂（测后还原）

    会话构造统一走 db_session（单一构造点）；端点与测试断言共享同一引擎同一库文件。
    """
    from platform_core.db import get_async_db

    async def _override_get_async_db() -> AsyncIterator["AsyncSession"]:
        async with db_session() as session:
            yield session

    app.dependency_overrides[get_async_db] = _override_get_async_db
    yield client
    # 恢复全局兜底 mock（而非 pop——防止后续 client 测试意外连真库）
    app.dependency_overrides[get_async_db] = _mock_async_db
