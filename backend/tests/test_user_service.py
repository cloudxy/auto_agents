"""用户管理服务单测 - UserService 分页列表（盲区补测）

约定：不连真实 MySQL，session 用 stubs.fake_async_session；Repository 方法
覆盖为 AsyncMock（服务层只负责 ORM 实体 → 响应契约的编排）。

覆盖（核心公开方法直测）：
- list_users：实体经 UserResponse.model_validate 映射 / total 汇总 /
  分页参数透传 / 空列表
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.user_service import UserService
from stubs import fake_async_session


def _user(**overrides) -> SimpleNamespace:
    """用户实体桩（UserResponse 契约字段，from_attributes 校验）"""
    defaults = dict(
        id=1, username="admin", email="admin@example.com",
        is_active=True, is_admin=True, role="admin",
        created_at=None, updated_at=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _service(users: list, total: int) -> UserService:
    svc = UserService(fake_async_session())
    svc.repo.list_users = AsyncMock(return_value=users)
    svc.repo.count_users = AsyncMock(return_value=total)
    return svc


# ---------------- list_users ----------------
@pytest.mark.asyncio
async def test_list_users_maps_entities_to_response_contract():
    """ORM 实体 → UserResponse 契约映射；total 取自 count_users"""
    svc = _service([_user(), _user(id=2, username="op", role="operator",
                                   is_admin=False)], total=2)

    resp = await svc.list_users()

    assert resp.total == 2
    assert [u.username for u in resp.items] == ["admin", "op"]
    assert resp.items[0].role == "admin"
    # 响应契约不含密码哈希等敏感字段
    assert "password" not in resp.items[0].model_dump()


@pytest.mark.asyncio
async def test_list_users_passes_pagination_to_repo():
    """分页参数原样透传 Repository（skip/limit）"""
    svc = _service([], total=0)

    await svc.list_users(skip=10, limit=5)

    svc.repo.list_users.assert_awaited_once_with(skip=10, limit=5)
    svc.repo.count_users.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_users_empty_returns_zero_total():
    """无用户：空列表 + total=0"""
    svc = _service([], total=0)

    resp = await svc.list_users()

    assert resp.total == 0
    assert resp.items == []
