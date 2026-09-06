"""L2 LiteLLM Admin API 客户端（禁直连其库）+ L5-1 主库会话隔离。"""
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.litellm.admin_client import LiteLlmAdminClient
from backend.services.litellm.admin_service import LiteLlmAdminService
from platform_core.exceptions import BusinessException
from platform_core.schemas.litellm import LitellmKeyCreate


@pytest.mark.asyncio
async def test_admin_disabled_raises():
    svc = LiteLlmAdminService(client=MagicMock())
    with patch("backend.services.litellm.admin_service.settings") as st:
        st.get.return_value = False
        with pytest.raises(BusinessException, match="未启用"):
            await svc.list_keys()


@pytest.mark.asyncio
async def test_ensure_tenant_key_noop_when_disabled():
    client = MagicMock()
    client.generate_key = AsyncMock()
    with patch("backend.services.litellm.admin_service.settings") as st:
        st.get.return_value = False
        await LiteLlmAdminService(client=client).ensure_tenant_key(9)
    client.generate_key.assert_not_called()


@pytest.mark.asyncio
async def test_create_key_calls_generate():
    client = MagicMock()
    client.generate_key = AsyncMock(return_value={"key": "sk-test", "key_alias": "t1"})
    with patch("backend.services.litellm.admin_service.settings") as st:
        st.get.return_value = True
        out = await LiteLlmAdminService(client=client).create_key(
            LitellmKeyCreate(key_alias="t1", max_budget=10)
        )
    assert out.token == "sk-test"
    client.generate_key.assert_awaited()


@pytest.mark.asyncio
async def test_admin_client_posts_key_generate():
    captured = {}

    async def handler(request):
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        import httpx
        return httpx.Response(200, json={"key": "sk-x", "key_alias": "a"})

    import httpx
    transport = httpx.MockTransport(handler)
    client = LiteLlmAdminClient(
        base_url="http://127.0.0.1:4000", master_key="sk-master", transport=transport,
    )
    data = await client.generate_key({"key_alias": "a"})
    assert data["key"] == "sk-x"
    assert captured["url"].endswith("/key/generate")
    assert captured["auth"] == "Bearer sk-master"


def test_main_async_session_uses_default_engine_not_newapi_db():
    from backend.services.newapi_api import _main_async_session

    src = inspect.getsource(_main_async_session)
    assert 'async_engines["DEFAULT"]' in src
    assert "NEWAPI" not in src


def test_tenant_admin_cannot_list_litellm_keys(admin_client):
    resp = admin_client.get("/api/v1/litellm/keys")
    assert resp.status_code in (401, 403)


def test_apply_proxy_route_off_by_default():
    from backend.services.llm_common.runtime import LlmRuntimeConfig, apply_proxy_route

    cfg = LlmRuntimeConfig(
        base_url="https://api.openai.com/v1", api_key="sk", model="m",
        temperature=0.2, timeout=10, max_retries=1, enabled=True, source="config",
    )
    out = apply_proxy_route(cfg)
    assert out.base_url == cfg.base_url
    assert out.source == "config"


def test_apply_proxy_route_rewrites_when_enabled(monkeypatch):
    from backend.services.llm_common import runtime as rt
    from backend.services.llm_common.runtime import LlmRuntimeConfig, apply_proxy_route

    class _S:
        def get(self, key, default=None):
            return {
                "LITELLM.PROXY.ROUTE_INTERNAL": True,
                "LITELLM.ADMIN.BASE_URL": "http://127.0.0.1:4000",
                "LITELLM.ADMIN.MASTER_KEY": "sk-master",
            }.get(key, default)

    monkeypatch.setattr(rt, "_seam", lambda: type("X", (), {"settings": _S()})())
    cfg = LlmRuntimeConfig(
        base_url="https://api.openai.com/v1", api_key="sk", model="m",
        temperature=0.2, timeout=10, max_retries=1, enabled=True, source="config",
    )
    out = apply_proxy_route(cfg)
    assert out.base_url == "http://127.0.0.1:4000"
    assert out.api_key == "sk-master"
    assert out.source == "proxy"
