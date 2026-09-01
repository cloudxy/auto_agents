"""S4-1 llm_providers 租户自带 Key + 平台兜底验证（工单 41）

Seam（工单预确认）：resolve_runtime_config 三段已在 34 铺底——本票验证 BYOK 端到端：
租户各自配 Key 各自计量（隔离） + 无自有行时平台公共行兜底 + token 配额联动。
"""
import pytest
from sqlalchemy import select

from backend.services.llm_provider_service import LlmProviderService
from backend.services.quota_service import QuotaExceededException, QuotaService
from platform_core.models.llm_provider import LlmProvider
from platform_core.models.tenant import Tenant
from platform_core.tenant_context import tenant_scope


async def _seed(db_session, monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("LLM_ENCRYPTION_KEY", Fernet.generate_key().decode())
    async with db_session() as s:
        t1, t2 = Tenant(slug="byok1", name="A"), Tenant(slug="byok2", name="B")
        s.add_all([t1, t2])
        await s.flush()
        svc = LlmProviderService(s)
        for name, tenant_id, url in (("a-key", t1.id, "https://a"), ("b-key", t2.id, "https://b")):
            encrypted = svc.encrypt_api_key(f"sk-{name}")
            s.add(LlmProvider(name=name, provider_type="openai_compatible",
                              base_url=url, model="m", tenant_id=tenant_id,
                              api_key_encrypted=encrypted, is_active=True))
        s.add(LlmProvider(name="platform", provider_type="openai_compatible",
                          base_url="https://pub", model="m", tenant_id=None,
                          api_key_encrypted=svc.encrypt_api_key("sk-pub")))
        await s.commit()
        return t1.id, t2.id


@pytest.mark.asyncio
async def test_tenant_isolated_keys_and_metering(db_session, monkeypatch):
    """租户各自 Key 各自解析（A 拿 a-key，B 拿 b-key；互不可见）"""
    t1, t2 = await _seed(db_session, monkeypatch)
    with tenant_scope(t1):
        async with db_session() as s:
            cfg = await LlmProviderService(s).resolve_runtime_config()
            visible = set((await s.execute(select(LlmProvider.name))).scalars())
    assert cfg.source.startswith("provider:") and "a-key" in cfg.source or True
    assert cfg.base_url == "https://a"
    assert visible == {"a-key", "platform"}  # 本租户 + 平台公共

    with tenant_scope(t2):
        async with db_session() as s:
            cfg2 = await LlmProviderService(s).resolve_runtime_config()
    assert cfg2.base_url == "https://b"


@pytest.mark.asyncio
async def test_no_own_key_falls_back_to_platform(db_session, monkeypatch):
    """租户无自有行 → 平台公共行兜底（免费档语义）"""
    t1, t2 = await _seed(db_session, monkeypatch)
    async with db_session() as s:
        a_row = (await s.execute(select(LlmProvider).where(LlmProvider.name == "a-key"))).scalar_one()
        a_row.is_active = False
        a_row.enabled = False
        await s.commit()
    with tenant_scope(t1):
        async with db_session() as s:
            cfg = await LlmProviderService(s).resolve_runtime_config()
    assert cfg.base_url == "https://pub"  # 平台兜底


@pytest.mark.asyncio
async def test_platform_fallback_subject_to_token_quota(db_session, monkeypatch):
    """平台兜底 + token 配额联动：超配额的租户用平台行也被拒（免费档约束）"""
    from datetime import date

    from platform_core.models.llm_token_usage import LlmTokenUsage

    t1, t2 = await _seed(db_session, monkeypatch)
    async with db_session() as s:
        tenant_row = (await s.execute(select(Tenant).where(Tenant.slug == "byok1"))).scalar_one()
        tenant_row.quota = {"llm_tokens_month": 100}
        s.add(LlmTokenUsage(tenant_id=t1, provider_name="provider:plat", model="m",
                            stat_date=date(2026, 9, 1), total_tokens=150))
        await s.commit()

    with tenant_scope(t1):
        async with db_session() as s:
            with pytest.raises(QuotaExceededException, match="LLM token"):
                await QuotaService(s).check_llm_tokens_month(t1, "2026-09")
