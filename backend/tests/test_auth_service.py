"""认证服务单元测试 - 用 Mock Repository 隔离，不连接真实数据库"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.auth_service import AuthService
from platform_core.exceptions import BusinessException


def _make_service() -> AuthService:
    """构造不触碰真实 DB 的 AuthService（session/repo 全部 mock）"""
    service = AuthService(session=AsyncMock())
    service.user_repo = AsyncMock()
    return service


def _make_user(password_hash: str, is_active: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        username="alice",
        email="alice@example.com",
        password_hash=password_hash,
        is_active=is_active,
        is_admin=False,
    )


class TestAuthenticate:
    """authenticate：用户验证逻辑"""

    @pytest.mark.asyncio
    async def test_authenticate_success(self):
        from backend.utils.auth import get_password_hash

        service = _make_service()
        service.user_repo.get_by_username.return_value = _make_user(
            get_password_hash("secret-123")
        )

        result = await service.authenticate("alice", "secret-123")

        assert result is not None
        assert result["username"] == "alice"
        assert result["is_admin"] is False
        service.user_repo.get_by_username.assert_awaited_once_with("alice")

    @pytest.mark.asyncio
    async def test_authenticate_unknown_user_returns_none(self):
        service = _make_service()
        service.user_repo.get_by_username.return_value = None

        assert await service.authenticate("ghost", "whatever") is None

    @pytest.mark.asyncio
    async def test_authenticate_inactive_user_returns_none(self):
        from backend.utils.auth import get_password_hash

        service = _make_service()
        service.user_repo.get_by_username.return_value = _make_user(
            get_password_hash("secret-123"), is_active=False
        )

        assert await service.authenticate("alice", "secret-123") is None

    @pytest.mark.asyncio
    async def test_authenticate_wrong_password_returns_none(self):
        from backend.utils.auth import get_password_hash

        service = _make_service()
        service.user_repo.get_by_username.return_value = _make_user(
            get_password_hash("secret-123")
        )

        assert await service.authenticate("alice", "wrong-password") is None


class TestCreateToken:
    """create_token：令牌签发"""

    @pytest.mark.asyncio
    async def test_create_token_returns_decodable_jwt(self):
        from backend.utils.auth import decode_access_token

        service = _make_service()
        user_data = {"id": 7, "username": "bob", "is_admin": True}

        token_resp = await service.create_token(user_data)

        assert token_resp.token_type == "bearer"
        assert token_resp.username == "bob"
        assert token_resp.is_admin is True
        payload = decode_access_token(token_resp.access_token)
        assert payload is not None
        assert payload["sub"] == "bob"
        assert payload["user_id"] == 7


class TestRegisterUser:
    """register_user：唯一性校验与创建流程"""

    @pytest.mark.asyncio
    async def test_register_duplicate_username_raises_business_exception(self):
        service = _make_service()
        service.user_repo.exists_by_username.return_value = True

        with pytest.raises(BusinessException) as exc_info:
            await service.register_user("alice", "alice@example.com", "secret-123")

        assert exc_info.value.code == "USERNAME_EXISTS"
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_register_duplicate_email_raises_business_exception(self):
        service = _make_service()
        service.user_repo.exists_by_username.return_value = False
        service.user_repo.exists_by_email.return_value = True

        with pytest.raises(BusinessException) as exc_info:
            await service.register_user("alice", "alice@example.com", "secret-123")

        assert exc_info.value.code == "EMAIL_EXISTS"

    @pytest.mark.asyncio
    async def test_register_success_commits_transaction(self):
        service = _make_service()
        service.user_repo.exists_by_username.return_value = False
        service.user_repo.exists_by_email.return_value = False
        service.user_repo.create.return_value = SimpleNamespace(
            id=9, username="alice", email="alice@example.com"
        )

        result = await service.register_user("alice", "alice@example.com", "secret-123")

        assert result == {"id": 9, "username": "alice", "email": "alice@example.com"}
        service.user_repo.create.assert_awaited_once()
        service.session.commit.assert_awaited_once()
