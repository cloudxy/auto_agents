"""pytest 全局 fixture - FastAPI TestClient 与环境准备

约定：
- 测试统一使用 local 环境配置（config/local/）
- 不连接真实 MySQL/Redis（涉及 DB 的测试用 mock 或跳过）
- 运行方式：uv run pytest -x -q backend/tests
"""
import os
import sys
from pathlib import Path

import pytest

# 确保仓库根目录在 sys.path（pytest 从任意层级调用时均可导入顶层包）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
