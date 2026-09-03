"""B-M1-2 探测端点验证（工单 21）：probe / probe-test / presets + key 三不红线

Seam（工单预确认）：/api/v1/llm/providers/models/* 端点（patch 适配层 execute_json，零真外呼）。
"""
import pytest
from sqlalchemy import func, select

import backend.services.llm_protocol.adapters as adapters_mod
from backend.services.llm_provider_service import LlmProviderService
from platform_core.models.llm_provider import LlmProvider
from platform_core.schemas.llm_provider import PROVIDER_TYPES

OPENAI_LIST = {
    "data": [
        {"id": "gpt-4o", "owned_by": "openai"},
        {"id": "gpt-4o-mini", "owned_by": "openai"},
        {"id": "text-embedding-3-small", "owned_by": "openai"},
    ]
}


def test_provider_types_extended():
    """schema 白名单扩为三协议（字面量对拍），旧值仍在"""
    assert PROVIDER_TYPES == ("openai_compatible", "anthropic", "google_gemini")


def test_platform_presets_endpoint(db_client, db_engine):
    resp = db_client.get("/api/v1/llm/providers/platform-presets")
    assert resp.status_code == 200
    presets = resp.json()["data"]
    names = {p["name"] for p in presets}
    assert len(presets) >= 12
    assert any("Ollama" in n for n in names)
    ollama = next(p for p in presets if "Ollama" in p["name"])
    assert ollama["base_url"].startswith("http://localhost:11434") and ollama["requires_key"] is False


def test_probe_models_parses_and_counts_chat_only(db_client, db_engine, monkeypatch, caplog):
    seen = {}

    async def _fake_execute(client, method, url, headers, json_payload=None):
        seen["url"], seen["auth"] = url, headers.get("Authorization")
        return OPENAI_LIST

    monkeypatch.setattr(adapters_mod, "execute_json", _fake_execute)
    resp = db_client.post(
        "/api/v1/llm/providers/models/probe",
        json={"provider_type": "openai_compatible", "base_url": "https://api.test/v1", "api_key": "sk-PROBE-SECRET"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [m["id"] for m in data["models"]] == ["gpt-4o", "gpt-4o-mini", "text-embedding-3-small"]
    assert data["chat_only_count"] == 2
    assert seen["url"] == "https://api.test/v1/models"
    assert seen["auth"] == "Bearer sk-PROBE-SECRET"
    # key 三不：响应不回显
    assert "sk-PROBE-SECRET" not in resp.text


@pytest.mark.asyncio
async def test_probe_key_never_logged_nor_persisted(db_client, db_engine, db_session, monkeypatch, caplog):
    """key 不写日志（caplog 全量扫描）且探测不产生任何 DB 行"""
    async def _fake_execute(client, method, url, headers, json_payload=None):
        return OPENAI_LIST

    monkeypatch.setattr(adapters_mod, "execute_json", _fake_execute)
    with caplog.at_level("DEBUG"):
        result = await LlmProviderService.probe_models(
            "openai_compatible", "https://api.test/v1", "sk-LOG-SECRET"
        )
    assert result["chat_only_count"] == 2
    assert all("sk-LOG-SECRET" not in (getattr(r, "message", "") or "") for r in caplog.records)

    async with db_session() as s:
        count = (await s.execute(select(func.count()).select_from(LlmProvider))).scalar_one()
    assert count == 0  # 纯内存探测，零落库


def test_probe_test_ok_and_error_masked(db_client, db_engine, monkeypatch):
    import backend.services.llm_probe_engine as probe_engine_mod
    from backend.services.llm_protocol import ProtocolError

    async def _ok(client, method, url, headers, json_payload=None):
        return {"choices": [{"message": {"content": "pong"}}]}

    async def _bad(client, method, url, headers, json_payload=None):
        raise ProtocolError("HTTP 401 Unauthorized")

    monkeypatch.setattr(adapters_mod, "execute_json", _ok)
    monkeypatch.setattr(probe_engine_mod, "execute_json", _ok)
    resp = db_client.post(
        "/api/v1/llm/providers/models/probe-test",
        json={"provider_type": "openai_compatible", "base_url": "https://api.test/v1",
              "api_key": "sk-x", "model": "gpt-4o"},
    )
    data = resp.json()["data"]
    assert data["ok"] is True and data["latency_ms"] >= 0 and data["model"] == "gpt-4o"

    monkeypatch.setattr(adapters_mod, "execute_json", _bad)
    monkeypatch.setattr(probe_engine_mod, "execute_json", _bad)
    resp2 = db_client.post(
        "/api/v1/llm/providers/models/probe-test",
        json={"provider_type": "openai_compatible", "base_url": "https://api.test/v1",
              "api_key": "sk-x", "model": "gpt-4o"},
    )
    data2 = resp2.json()["data"]
    assert data2["ok"] is False and "401" in data2["error"]


def test_create_provider_accepts_anthropic_type(db_client, db_engine, db_session):
    """provider_type 三协议全可入库（无 api_key 路径），旧协议回归"""
    resp = db_client.post(
        "/api/v1/llm/providers",
        json={"name": "anthropic-official", "provider_type": "anthropic",
              "base_url": "https://api.anthropic.com", "model": "claude-sonnet-4-6"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["provider_type"] == "anthropic"

    resp2 = db_client.post(
        "/api/v1/llm/providers",
        json={"name": "legacy-openai", "provider_type": "openai_compatible",
              "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    )
    assert resp2.status_code == 200
