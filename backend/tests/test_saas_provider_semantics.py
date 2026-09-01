"""S1-4 llm_providers 租户语义验证（工单 34）：互斥收窄 + 三段解析

Seam（工单预确认）：activate_exclusive / resolve_runtime_config。
"""
import pytest
from sqlalchemy import select

from backend.services.llm_provider_service import LlmProviderService
from platform_core.models.llm_provider import LlmProvider
from platform_core.models.tenant import Tenant
from platform_core.tenant_context import tenant_scope


async def _seed(db_session):
    async with db_session() as s:
        t1 = Tenant(slug="t1", name="T1")
        t2 = Tenant(slug="t2", name="T2")
        s.add_all([t1, t2])
        await s.flush()
        s.add_all([
            LlmProvider(name="p1-a", provider_type="openai_compatible",
                        base_url="https://a1", model="m", tenant_id=t1.id, is_active=True),
            LlmProvider(name="p2-a", provider_type="openai_compatible",
                        base_url="https://a2", model="m", tenant_id=t2.id, is_active=True),
            LlmProvider(name="platform-pub", provider_type="openai_compatible",
                        base_url="https://pub", model="m", tenant_id=None, enabled=True),
        ])
        await s.commit()
        return t1.id, t2.id


@pytest.mark.asyncio
async def test_mutual_exclusion_scoped_to_tenant(db_session):
    """两租户各自激活互不影响（10.2-B）；平台公共行不被动"""
    t1, t2 = await _seed(db_session)
    async with db_session() as s:
        repo = __import__("backend.repositories.llm_provider_repository", fromlist=["LlmProviderRepository"]).LlmProviderRepository(s)
        target = (await s.execute(select(LlmProvider).where(LlmProvider.name == "p1-a"))).scalar_one()
        await repo.activate_exclusive(target.id)  # 在 t1 域内切换
        await s.commit()

    async with db_session() as s:
        actives = {p.name for p in (await s.execute(
            select(LlmProvider).where(LlmProvider.is_active == True)  # noqa: E712
        )).scalars()}
    # t1 的目标行仍激活；t2 激活位不受扰
    assert "p1-a" in actives and "p2-a" in actives


@pytest.mark.asyncio
async def test_resolve_prefers_tenant_then_platform(db_session, monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("LLM_ENCRYPTION_KEY", Fernet.generate_key().decode())
    t1, t2 = await _seed(db_session)
    async with db_session() as s:
        svc = LlmProviderService(s)
        for name in ("p1-a", "platform-pub"):
            row = (await s.execute(select(LlmProvider).where(LlmProvider.name == name))).scalar_one()
            row.api_key_encrypted = svc.encrypt_api_key("sk-test")
        await s.commit()

    # 租户 1 有自有激活行 → 用自有
    with tenant_scope(t1):
        async with db_session() as s:
            cfg = await LlmProviderService(s).resolve_runtime_config()
    assert cfg.source == "provider:1" and cfg.base_url == "https://a1"

    # 租户 1 停用自有行 → 平台公共行兜底
    with tenant_scope(t1):
        async with db_session() as s:
            row = (await s.execute(select(LlmProvider).where(LlmProvider.name == "p1-a"))).scalar_one()
            row.is_active = False
            row.enabled = False
            await s.commit()
            cfg = await LlmProviderService(s).resolve_runtime_config()
    assert cfg.base_url == "https://pub"
