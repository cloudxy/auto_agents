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


@pytest.fixture(scope="session")
def app():
    """FastAPI 应用实例（含异常处理器与全量路由）

    测试环境全局 override 鉴权依赖：端点测试默认以 admin 身份通过，
    RBAC 守卫自身的 401/403 分支由 test_rbac_audit.py 直接单测。
    """
    from backend.app import create_app
    from backend.app.api.deps import CurrentUser, get_current_user

    application = create_app()

    async def _override_current_user():
        return CurrentUser(id=1, username="test-admin", role="admin")

    application.dependency_overrides[get_current_user] = _override_current_user
    return application


@pytest.fixture(scope="session")
def client(app):
    """FastAPI TestClient（同步 HTTP 测试入口）"""
    from fastapi.testclient import TestClient

    return TestClient(app)


# ---------------------------------------------------------------------------
# DB fixture（E0.1a 工单 01）：SQLite 会话与测试间隔离
#
# 约束：
# - TestClient 每请求新建事件循环，引擎必须 NullPool（连接不跨循环复用），
#   与 platform_core/db.py 的 pytest 态处理同一口径；
# - 每测试独立 tmp 文件库（非共享内存库）——隔离即"全新库"，唯一键冲突不可能跨测试出现；
# - MySQL 保真通道（MYSQL_FIDELITY）属工单 03，本组 fixture 不感知。
# ---------------------------------------------------------------------------


@pytest.fixture
def db_engine(tmp_path: Path) -> Iterator["AsyncEngine"]:
    """每测试独立的 SQLite 异步引擎（create_all 建全部 ORM 表）"""
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    import platform_core.models  # noqa: F401 触发全模型注册到 Base.metadata
    from platform_core.models.base import Base

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        poolclass=NullPool,
    )

    async def _create_all() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create_all())
    yield engine
    asyncio.run(engine.dispose())


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
    app.dependency_overrides.pop(get_async_db, None)
