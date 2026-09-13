"""S4-1 llm_providers 租户自带 Key + 平台兜底验证（工单 41）

Seam（工单预确认）：resolve_runtime_config 三段已在 34 铺底——本票验证 BYOK 端到端：
租户各自配 Key 各自计量（隔离） + 无自有行时平台公共行兜底 + token 配额联动。
"""
import pytest
from sqlalchemy import select

from backend.services.llm_provider_service import LlmProviderService
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
            a_id = (await s.execute(
                select(LlmProvider.id).where(LlmProvider.name == "a-key")
            )).scalar_one()
    assert (
        cfg.source.startswith("provider:")
        and cfg.source == f"provider:{a_id}"
        and cfg.provider_id == a_id
        and cfg.base_url == "https://a"
        and "a-key" in visible
        and "b-key" not in visible
    )
    assert visible == {"a-key", "platform"}  # 本租户 + 平台公共

    with tenant_scope(t2):
        async with db_session() as s:
            cfg2 = await LlmProviderService(s).resolve_runtime_config()
            visible2 = set((await s.execute(select(LlmProvider.name))).scalars())
            b_id = (await s.execute(
                select(LlmProvider.id).where(LlmProvider.name == "b-key")
            )).scalar_one()
    assert (
        cfg2.source.startswith("provider:")
        and cfg2.source == f"provider:{b_id}"
        and cfg2.provider_id == b_id
        and cfg2.base_url == "https://b"
        and "b-key" in visible2
        and "a-key" not in visible2
    )
    assert cfg.provider_id != cfg2.provider_id


@pytest.mark.asyncio
async def test_no_own_key_falls_back_to_platform(db_session, monkeypatch):
    """T-16 SH-01：无自有行 outbound=网关 URL，不是 https://pub。"""
    import backend.services.ai_planner.llm_client as lc
    import backend.services.ai_planner_service as aps
    from config import settings

    t1, t2 = await _seed(db_session, monkeypatch)
    async with db_session() as s:
        a_row = (await s.execute(select(LlmProvider).where(LlmProvider.name == "a-key"))).scalar_one()
        a_row.is_active = False
        a_row.enabled = False
        await s.commit()

    prev_plane = settings.get("LLM.DATA_PLANE")
    prev_base = settings.get("LITELLM.BASE_URL")
    settings.set("LLM.DATA_PLANE", "litellm")
    settings.set("LITELLM.BASE_URL", "http://gw.test")
    settings.set("LITELLM.MASTER_KEY", "sk-virt")
    settings.set("LLM.MAX_RETRIES", 1)
    outbound: list[str] = []

    async def _http(method, path, **_kw):
        url = f"http://gw.test{path}"
        if method == "GET" and path == "/v1/models":
            return {"data": [{"id": "m"}]}
        if method == "POST" and path == "/v1/chat/completions":
            outbound.append(url)
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"total_tokens": 1, "prompt_tokens": 1, "completion_tokens": 0},
            }
        raise AssertionError(path)

    async def _month(*_a, **_k):
        return 0

    async def _sleep(*_a, **_k):
        return None

    def _boom():
        raise AssertionError("SH-16: except 禁止 resolve_config_from_settings")

    monkeypatch.setattr("backend.services.llm_gateway._settings._http_json", _http)
    monkeypatch.setattr("backend.services.llm_gateway.chat._http_json", _http)
    monkeypatch.setattr(aps, "quota_session_factory", db_session, raising=False)
    monkeypatch.setattr(lc, "get_month_used", _month)
    monkeypatch.setattr(lc.asyncio, "sleep", _sleep)
    monkeypatch.setattr(lc, "resolve_config_from_settings", _boom)
    try:
        with tenant_scope(t1):
            content = await lc.llm_chat([{"role": "user", "content": "hi"}])
        assert content == "ok"
        assert outbound == ["http://gw.test/v1/chat/completions"]
        assert all("https://pub" not in u for u in outbound)
        assert t2
    finally:
        if prev_plane is not None:
            settings.set("LLM.DATA_PLANE", prev_plane)
        if prev_base is not None:
            settings.set("LITELLM.BASE_URL", prev_base)


@pytest.mark.asyncio
async def test_platform_fallback_subject_to_token_quota(db_session, monkeypatch):
    """平台兜底 + token 配额联动：满额拒绝发生在真正 HTTP 出站前。"""
    from datetime import date

    import backend.services.ai_planner_service as aps
    import backend.services.ai_planner.llm_client as lc
    from backend.services.llm_common import LlmRuntimeConfig
    from platform_core.exceptions import BusinessException
    from backend.services.quota_service import PLAN_FULL_CTA, PLAN_FULL_USER
    from platform_core.models.llm_token_usage import LlmTokenUsage

    t1, t2 = await _seed(db_session, monkeypatch)
    async with db_session() as s:
        tenant_row = (await s.execute(select(Tenant).where(Tenant.slug == "byok1"))).scalar_one()
        tenant_row.quota = {"llm_tokens_month": 100}
        a_row = (await s.execute(select(LlmProvider).where(LlmProvider.name == "a-key"))).scalar_one()
        a_row.is_active = False
        a_row.enabled = False
        s.add(LlmTokenUsage(tenant_id=t1, provider_name="provider:plat", model="m",
                            stat_date=date(2026, 9, 1), total_tokens=150))
        await s.commit()

    outbound: list = []

    async def _resolve():
        return LlmRuntimeConfig(
            base_url="https://pub", api_key="sk-pub", model="m",
            temperature=0.2, timeout=5, max_retries=1, enabled=True,
            source="provider:platform", provider_id=None, protocol="openai_compatible",
        )

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None):
            outbound.append({"url": url})
            raise AssertionError("套餐闸必须在出站 HTTP 前拒绝")

    monkeypatch.setattr(
        "backend.services.ai_planner_service._resolve_llm_runtime_config", _resolve,
    )
    monkeypatch.setattr(aps, "quota_session_factory", db_session, raising=False)
    monkeypatch.setattr(lc.httpx, "AsyncClient", _Client)

    with tenant_scope(t1):
        with pytest.raises(BusinessException) as ei:
            await lc.llm_chat([{"role": "user", "content": "hi"}])
    assert ei.value.code == "TASK_QUOTA_LIMIT_REACHED"
    assert ei.value.status_code != 429
    assert PLAN_FULL_USER in ei.value.message
    assert PLAN_FULL_CTA in ei.value.message
    assert "QUOTA_EXCEEDED" not in ei.value.message
    assert "采集未运行，不会出数" not in ei.value.message
    assert outbound == []
    assert t2  # 对照租户已种子，本夹具只闸 t1
