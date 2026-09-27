"""T-15：llm_gateway 拆 chat vs admin；__all__ 不同时含二者；叶可 import。

不改四动作解析（T-16）；不把 llm_chat 挪出 ai_planner。
"""
from pathlib import Path

import httpx
import pytest

from backend.services import llm_gateway
from backend.services.llm_gateway import admin as admin_mod
from backend.services.llm_gateway.chat import chat_completions

REPO = Path(__file__).resolve().parents[2]
GW_DIR = REPO / "backend" / "services" / "llm_gateway"
ARCH_SH = REPO / "tools" / "check" / "arch.sh"
LLM_CLIENT = REPO / "backend" / "services" / "ai_planner" / "llm_client.py"


def test_gateway_source_files_exist():
    assert (GW_DIR / "chat.py").is_file()
    assert (GW_DIR / "admin.py").is_file()
    assert (GW_DIR / "__init__.py").is_file()
    assert not (GW_DIR / "chat.py").read_text(encoding="utf-8").strip() == ""
    assert not (GW_DIR / "admin.py").read_text(encoding="utf-8").strip() == ""


def test_init_all_does_not_export_chat_and_admin_together():
    exported = set(getattr(llm_gateway, "__all__", []))
    assert not {"chat", "admin"} <= exported


def test_chat_and_admin_are_separate_modules():
    chat_src = (GW_DIR / "chat.py").read_text(encoding="utf-8")
    admin_src = (GW_DIR / "admin.py").read_text(encoding="utf-8")
    assert "llm_gateway.admin" not in chat_src
    assert "llm_gateway.chat" not in admin_src
    assert "create_async_engine(" not in chat_src
    assert "create_async_engine(" not in admin_src
    assert "DB_DSN" not in chat_src
    assert "DB_DSN" not in admin_src


def test_llm_client_imports_chat_not_admin():
    src = LLM_CLIENT.read_text(encoding="utf-8")
    assert "llm_gateway.chat" in src
    assert "llm_gateway.admin" not in src
    assert "def llm_chat" in src or "async def llm_chat" in src


def test_arch_sh_has_verbatim_b4_greps():
    text = ARCH_SH.read_text(encoding="utf-8")
    assert (
        r"^(from|import) backend\.services\.(spider_|newapi_|litellm_|relay_|channel_|ai_planner|llm_gateway)"
        in text
    )
    assert (
        r"from backend\.services\.llm_gateway\.admin|import backend\.services\.llm_gateway\.admin|from backend\.services\.llm_gateway import admin"
        in text
    )
    assert (
        r"from backend\.services\.llm_gateway\.chat|import backend\.services\.llm_gateway\.chat|from backend\.services\.llm_gateway import chat"
        in text
    )
    assert "--exclude=llm_client.py" in text
    assert "backend/services/power_market/" in text


def test_chat_is_importable_for_llm_client():
    assert callable(chat_completions)


@pytest.mark.asyncio
async def test_chat_completions_posts_only_v1_path(monkeypatch):
    monkeypatch.setattr(
        "backend.services.llm_gateway._settings._base_url", lambda: "http://gw.test",
    )
    monkeypatch.setattr(
        "backend.services.llm_gateway._settings._auth_headers",
        lambda: {"Authorization": "Bearer sk-virt", "Content-Type": "application/json"},
    )
    monkeypatch.setattr(
        "backend.services.llm_gateway._settings._timeout_sec", lambda: 5.0,
    )
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["method"] = request.method
        seen["auth"] = request.headers.get("Authorization") or ""
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
            request=request,
        )

    body = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}
    data = await chat_completions(body, transport=httpx.MockTransport(handler))
    assert seen["url"] == "http://gw.test/v1/chat/completions"
    assert seen["method"] == "POST"
    assert seen["auth"] == "Bearer sk-virt"
    assert data["choices"][0]["message"]["content"] == "ok"


@pytest.mark.asyncio
async def test_admin_http_models_deployments_spend_budget(monkeypatch):
    monkeypatch.setattr(
        "backend.services.llm_gateway._settings._base_url", lambda: "http://gw.test",
    )
    monkeypatch.setattr(
        "backend.services.llm_gateway._settings._auth_headers",
        lambda: {"Authorization": "Bearer sk-virt", "Content-Type": "application/json"},
    )
    monkeypatch.setattr(
        "backend.services.llm_gateway._settings._timeout_sec", lambda: 5.0,
    )
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url)))
        return httpx.Response(200, json={"data": []}, request=request)

    transport = httpx.MockTransport(handler)
    await admin_mod.list_models(transport=transport)
    await admin_mod.list_deployments(transport=transport)
    await admin_mod.get_spend_logs(transport=transport)
    await admin_mod.get_global_spend(transport=transport)
    await admin_mod.list_budgets(transport=transport)
    await admin_mod.create_budget({"max_budget": 1}, transport=transport)
    await admin_mod.get_budget_info("b1", transport=transport)
    await admin_mod.update_budget({"budget_id": "b1", "max_budget": 2}, transport=transport)
    assert ("GET", "http://gw.test/model/info") in seen
    assert ("GET", "http://gw.test/v2/model/info") in seen
    assert ("GET", "http://gw.test/spend/logs") in seen
    assert ("GET", "http://gw.test/global/spend") in seen
    assert ("GET", "http://gw.test/budget/list") in seen
    assert ("POST", "http://gw.test/budget/new") in seen
    assert any(m == "GET" and u.startswith("http://gw.test/budget/info") for m, u in seen)
    assert ("POST", "http://gw.test/budget/update") in seen


@pytest.mark.asyncio
async def test_list_key_spend_logs_filters_v1_api_key_and_wraps_list(monkeypatch):
    monkeypatch.setattr(
        "backend.services.llm_gateway._settings._base_url", lambda: "http://gw.test",
    )
    monkeypatch.setattr(
        "backend.services.llm_gateway._settings._auth_headers",
        lambda: {"Authorization": "Bearer sk-virt", "Content-Type": "application/json"},
    )
    monkeypatch.setattr(
        "backend.services.llm_gateway._settings._timeout_sec", lambda: 5.0,
    )
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            200,
            json=[{"total_tokens": 39, "api_key": "abc"}],
            request=request,
        )

    data = await admin_mod.list_key_spend_logs(
        "abc", transport=httpx.MockTransport(handler),
    )
    assert len(seen) == 1
    assert seen[0].startswith("http://gw.test/spend/logs")
    assert "api_key=abc" in seen[0]
    assert "/spend/logs/v2" not in seen[0]
    assert data["data"][0]["total_tokens"] == 39
    assert data["total_pages"] == 1
