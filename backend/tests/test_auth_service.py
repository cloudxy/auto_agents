"""认证服务单元测试 - 用 Mock Repository 隔离，不连接真实数据库"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.auth_service import AuthService
from platform_core.exceptions import BusinessException


def _make_service() -> AuthService:
    """构造不触碰真实 DB 的 AuthService（session/repo 全部 mock）

    session.execute 桩为 default 租户行（T5 后 register_user 前置查询；
    AsyncMock 的 return_value 会传染 async 类型，须显式给同步桩）。
    """
    session = AsyncMock()
    tenant_row = MagicMock()
    tenant_row.scalar_one_or_none.return_value = SimpleNamespace(id=1, slug="default")
    session.execute = AsyncMock(return_value=tenant_row)
    service = AuthService(session=session)
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
    """authenticate：用户验证逻辑（T5 后 get_by_username 返回 list 候选 + 密码消歧）"""

    @pytest.mark.asyncio
    async def test_authenticate_success(self):
        from backend.utils.auth import get_password_hash

        service = _make_service()
        service.user_repo.get_by_username.return_value = [
            _make_user(get_password_hash("secret-123"))]

        result = await service.authenticate("alice", "secret-123")

        assert result is not None
        assert result["username"] == "alice"
        assert result["is_admin"] is False
        service.user_repo.get_by_username.assert_awaited_once_with("alice")

    @pytest.mark.asyncio
    async def test_authenticate_unknown_user_returns_none(self):
        service = _make_service()
        service.user_repo.get_by_username.return_value = []

        assert await service.authenticate("ghost", "whatever") is None

    @pytest.mark.asyncio
    async def test_authenticate_inactive_user_returns_none(self):
        from backend.utils.auth import get_password_hash

        service = _make_service()
        service.user_repo.get_by_username.return_value = [
            _make_user(get_password_hash("secret-123"), is_active=False)]

        assert await service.authenticate("alice", "secret-123") is None

    @pytest.mark.asyncio
    async def test_authenticate_wrong_password_returns_none(self):
        from backend.utils.auth import get_password_hash

        service = _make_service()
        service.user_repo.get_by_username.return_value = [
            _make_user(get_password_hash("secret-123"))]

        assert await service.authenticate("alice", "wrong-password") is None

    @pytest.mark.asyncio
    async def test_authenticate_cross_tenant_unique_match_wins(self):
        """多行候选（跨租户同名）：唯一密码命中者胜出（T5 决策 A）"""
        from backend.utils.auth import get_password_hash

        service = _make_service()
        service.user_repo.get_by_username.return_value = [
            _make_user(get_password_hash("alpha-pass"), is_active=True),
            _make_user(get_password_hash("beta-pass"), is_active=True),
        ]

        result = await service.authenticate("alice", "beta-pass")

        assert result is not None
        assert result["username"] == "alice"

    @pytest.mark.asyncio
    async def test_authenticate_cross_tenant_no_match_returns_none(self):
        """多行候选皆不中：401 语义（None），不泄露候选数"""
        from backend.utils.auth import get_password_hash

        service = _make_service()
        service.user_repo.get_by_username.return_value = [
            _make_user(get_password_hash("alpha-pass")),
            _make_user(get_password_hash("beta-pass")),
        ]

        assert await service.authenticate("alice", "wrong-password") is None

    @pytest.mark.asyncio
    async def test_authenticate_cross_tenant_multi_match_returns_none(self):
        """多行候选同密码（凭据无法消歧）：401 语义（None）"""
        from backend.utils.auth import get_password_hash

        service = _make_service()
        service.user_repo.get_by_username.return_value = [
            _make_user(get_password_hash("same-pass")),
            _make_user(get_password_hash("same-pass")),
        ]

        assert await service.authenticate("alice", "same-pass") is None


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
    """register_user：唯一性校验与创建流程（T5 后挂 default 租户）

    session 为 AsyncMock：default 租户查询（session.execute→scalar_one_or_none）
    默认返回 truthy MagicMock，租户兜底分支视为命中，无需逐用例桩。
    """

    @pytest.mark.asyncio
    async def test_register_duplicate_username_raises_business_exception(self):
        service = _make_service()
        service.user_repo.exists_username_in_tenant.return_value = True

        with pytest.raises(BusinessException) as exc_info:
            await service.register_user("alice", "alice@example.com", "secret-123")

        assert exc_info.value.code == "USERNAME_EXISTS"
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_register_duplicate_email_raises_business_exception(self):
        service = _make_service()
        service.user_repo.exists_username_in_tenant.return_value = False
        service.user_repo.exists_by_email.return_value = True

        with pytest.raises(BusinessException) as exc_info:
            await service.register_user("alice", "alice@example.com", "secret-123")

        assert exc_info.value.code == "EMAIL_EXISTS"

    @pytest.mark.asyncio
    async def test_register_success_commits_transaction(self):
        service = _make_service()
        service.user_repo.exists_username_in_tenant.return_value = False
        service.user_repo.exists_by_email.return_value = False
        service.user_repo.create.return_value = SimpleNamespace(
            id=9, username="alice", email="alice@example.com"
        )

        result = await service.register_user("alice", "alice@example.com", "secret-123")

        assert result == {"id": 9, "username": "alice", "email": "alice@example.com"}
        service.user_repo.create.assert_awaited_once()
        # T5 决策 B：公开注册必须挂 default 租户（tenant_role=viewer），不再产 NULL 行
        create_kwargs = service.user_repo.create.await_args.kwargs
        assert create_kwargs.get("tenant_role") == "viewer"
        assert create_kwargs.get("tenant_id") is not None
        service.session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_register_without_default_tenant_is_503(self):
        """default 租户缺失（环境未初始化）→ 503 优雅报错而非 500"""
        from unittest.mock import MagicMock

        service = _make_service()
        no_row = MagicMock()
        no_row.scalar_one_or_none.return_value = None
        service.session.execute = AsyncMock(return_value=no_row)

        with pytest.raises(BusinessException) as exc_info:
            await service.register_user("alice", "alice@example.com", "secret-123")

        assert exc_info.value.status_code == 503
