"""RBAC 角色守卫 + 操作审计单测

覆盖：
- effective_role 角色解析（is_admin 兼容）
- require_role 守卫放行/403
- get_current_user 401 分支（无 Token / 无效 Token / 用户缺失 / 已停用）
- AuditService 审计落参（detail JSON 序列化、异常吞掉）
- 角色权限映射完整性
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from backend.app.api.deps import (
    CurrentUser,
    effective_role,
    get_current_user,
    require_admin,
    require_login,
    require_role,
)
from backend.app.api.v1.auth import _ROLE_PERMISSIONS
from backend.services.audit_service import AuditService
from backend.utils.auth import create_access_token
from platform_core.exceptions import AuthenticationException, AuthorizationException
from platform_core.models.user import User


def _user(**overrides) -> User:
    u = User()
    u.id = 1
    u.username = "tester"
    u.is_active = True
    u.is_admin = False
    u.role = "operator"
    for k, v in overrides.items():
        setattr(u, k, v)
    return u


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _snapshot(role: str) -> CurrentUser:
    return CurrentUser(id=1, username="tester", role=role)


# ---------------- effective_role ----------------
def test_effective_role_is_admin_wins():
    assert effective_role(_user(is_admin=True, role="viewer")) == "admin"


def test_effective_role_from_role_column():
    assert effective_role(_user(role="viewer")) == "viewer"


def test_effective_role_fallback_operator():
    assert effective_role(_user(role=None)) == "operator"


# ---------------- require_role 守卫（接收鉴权层快照） ----------------
@pytest.mark.asyncio
async def test_require_admin_passes_admin():
    snap = _snapshot("admin")
    result = await require_admin(user=snap)
    assert result is snap


@pytest.mark.asyncio
async def test_require_admin_rejects_operator():
    with pytest.raises(AuthorizationException):
        await require_admin(user=_snapshot("operator"))


@pytest.mark.asyncio
async def test_require_login_passes_viewer():
    snap = _snapshot("viewer")
    result = await require_login(user=snap)
    assert result is snap


@pytest.mark.asyncio
async def test_require_role_custom_roles():
    guard = require_role("viewer")
    await guard(user=_snapshot("viewer"))  # 放行
    with pytest.raises(AuthorizationException):
        await guard(user=_snapshot("admin"))  # admin 不在白名单


# ---------------- get_current_user 401 分支 ----------------
@pytest.mark.asyncio
async def test_current_user_missing_credentials():
    with pytest.raises(AuthenticationException):
        await get_current_user(credentials=None, session=AsyncMock())


@pytest.mark.asyncio
async def test_current_user_invalid_token():
    with pytest.raises(AuthenticationException):
        await get_current_user(credentials=_credentials("not-a-jwt"), session=AsyncMock())


@pytest.mark.asyncio
async def test_current_user_not_found():
    token = create_access_token({"sub": "ghost", "user_id": 999})
    session = AsyncMock()
    session.get.return_value = None
    with pytest.raises(AuthenticationException):
        await get_current_user(credentials=_credentials(token), session=session)


@pytest.mark.asyncio
async def test_current_user_inactive():
    token = create_access_token({"sub": "tester", "user_id": 1})
    session = AsyncMock()
    session.get.return_value = _user(is_active=False)
    with pytest.raises(AuthenticationException):
        await get_current_user(credentials=_credentials(token), session=session)


@pytest.mark.asyncio
async def test_current_user_ok():
    token = create_access_token({"sub": "tester", "user_id": 1})
    session = AsyncMock()
    session.get.return_value = _user()
    result = await get_current_user(credentials=_credentials(token), session=session)
    # 返回纯快照（避免 commit 后过期属性惰性加载抛 MissingGreenlet）
    assert isinstance(result, CurrentUser)
    assert result.id == 1
    assert result.username == "tester"
    assert result.role == "operator"


@pytest.mark.asyncio
async def test_current_user_snapshot_is_admin_maps_admin():
    token = create_access_token({"sub": "tester", "user_id": 1})
    session = AsyncMock()
    session.get.return_value = _user(is_admin=True, role="viewer")
    result = await get_current_user(credentials=_credentials(token), session=session)
    assert result.role == "admin"


# ---------------- AuditService ----------------
@pytest.mark.asyncio
async def test_audit_record_serializes_detail():
    svc = AuditService(session=MagicMock())
    svc.repo = MagicMock()
    svc.repo.create = AsyncMock()
    await svc.record(1, "admin", "task.run", "task#12", {"spider": "example"})
    svc.repo.create.assert_awaited_once()
    kwargs = svc.repo.create.await_args.kwargs
    assert kwargs["action"] == "task.run"
    assert kwargs["detail"] == '{"spider": "example"}'


@pytest.mark.asyncio
async def test_audit_record_swallows_errors():
    svc = AuditService(session=MagicMock())
    svc.repo = MagicMock()
    svc.repo.create = AsyncMock(side_effect=RuntimeError("db down"))
    # 不应抛出异常（审计失败不阻断主流程）
    await svc.record(1, "admin", "task.delete", "task#12")


# ---------------- 权限映射 ----------------
def test_role_permissions_mapping():
    assert set(_ROLE_PERMISSIONS.keys()) == {"admin", "operator", "viewer"}
    assert "btn:delete" in _ROLE_PERMISSIONS["admin"]
    assert "btn:schedule" in _ROLE_PERMISSIONS["admin"]
    assert "btn:delete" not in _ROLE_PERMISSIONS["operator"]
    assert "btn:create" not in _ROLE_PERMISSIONS["viewer"]


# ---------------- HTTP 级门禁（无 override，证明真实生效） ----------------
def test_unauthenticated_request_rejected_401():
    from fastapi.testclient import TestClient

    from backend.app import create_app

    app = create_app()  # 不注入 dependency_overrides
    client = TestClient(app)
    resp = client.get("/api/v1/spiders/tasks")
    assert resp.status_code == 401
    resp_admin = client.get("/api/v1/admin/users")
    assert resp_admin.status_code == 401
