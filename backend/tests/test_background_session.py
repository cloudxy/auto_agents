"""R1（工单44）BackgroundSession 深模块：scope 派生 + 默认租户"""
import pytest
from sqlalchemy import select

from backend.services.background_session import _anchor_tenant_id, background_session, default_tenant_id
from platform_core.models.tenant import Tenant
from platform_core.tenant_context import current_tenant_id, is_platform_mode


class _Task:
    tenant_id = 7


def test_anchor_extraction():
    assert _anchor_tenant_id(_Task()) == 7
    assert _anchor_tenant_id({"tenant_id": 9}) == 9
    assert _anchor_tenant_id(None) is None
    assert _anchor_tenant_id(object()) is None  # 无属性 → 平台域


@pytest.mark.asyncio
async def test_scope_derivation(db_session, monkeypatch):
    """有锚 → tenant_scope；无锚 → platform_scope（session 由注入桩替身）"""
    opened = {}

    class _FakeSession:
        def __init__(self, engine):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    import platform_core.db as db_mod

    monkeypatch.setattr(db_mod, "AsyncSession", _FakeSession)
    monkeypatch.setattr(db_mod, "get_manager",
                        lambda: type("M", (), {"async_engines": {"DEFAULT": object()}})())

    async with background_session(anchor=_Task()):
        assert current_tenant_id() == 7 and not is_platform_mode()
        opened["tenant"] = True
    assert current_tenant_id() is None  # 退出即还原

    async with background_session():
        assert is_platform_mode() and current_tenant_id() is None
        opened["platform"] = True
    assert not is_platform_mode()
    assert opened == {"tenant": True, "platform": True}


@pytest.mark.asyncio
async def test_default_tenant_get_or_create(db_session):
    async with db_session() as s:
        first = await default_tenant_id(s)
        await s.commit()
    async with db_session() as s:
        second = await default_tenant_id(s)
        rows = (await s.execute(select(Tenant).where(Tenant.slug == "default"))).scalars().all()
    assert first == second and len(rows) == 1  # 幂等
