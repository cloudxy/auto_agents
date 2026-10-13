"""backend/scripts/set_admin_account.py 回归：走 get_async_session 的默认会话跑完整 main()。

get_async_session 用 AsyncSession(engine)，expire_on_commit 默认 True：commit 之后再读
ORM 对象属性会触发异步惰性加载 → sqlalchemy.exc.MissingGreenlet。脚本曾在建号 commit
之后读 platform_tenant.id，结果账号建了、脚本却崩在打印前。
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import backend.scripts.set_admin_account as script
from backend.utils.auth import verify_password
from platform_core.models.tenant import Tenant
from platform_core.models.user import User


@pytest.fixture
def platform_tenant_id(db_engine, monkeypatch) -> int:
    import platform_core.db as db

    async def _seed() -> int:
        async with AsyncSession(db_engine, expire_on_commit=False) as s:
            tenant = Tenant(slug="platform", name="平台")
            s.add(tenant)
            await s.commit()
            return int(tenant.id)

    monkeypatch.setattr(script, "init_db", lambda: None)  # db_engine 已注入 DEFAULT 引擎，不连真库
    monkeypatch.setattr(db.get_manager(), "_ready", True)
    return asyncio.run(_seed())


def _admin_row(db_engine, tenant_id: int) -> User:
    async def _load() -> User:
        async with AsyncSession(db_engine, expire_on_commit=False) as s:
            return (await s.execute(select(User).where(
                User.username == script.USERNAME, User.tenant_id == tenant_id))).scalar_one()

    return asyncio.run(_load())


def test_main_creates_platform_admin_without_missing_greenlet(db_engine, platform_tenant_id, capsys):
    asyncio.run(script.main())
    out = capsys.readouterr().out
    assert "已创建平台超管账号" in out and "密码校验通过" in out
    row = _admin_row(db_engine, platform_tenant_id)
    assert row.is_platform_admin and verify_password(script.PASSWORD, row.password_hash)


def test_main_second_run_resets_existing_admin(db_engine, platform_tenant_id, capsys):
    asyncio.run(script.main())
    capsys.readouterr()
    asyncio.run(script.main())
    out = capsys.readouterr().out
    assert "已重置平台超管账号密码" in out and "密码校验通过" in out
