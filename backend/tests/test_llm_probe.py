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


def test_probe_models_parses_and_counts_chat_only(db_client, admin_client, db_engine, monkeypatch, caplog):
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


def test_probe_test_ok_and_error_masked(db_client, admin_client, db_engine, monkeypatch):
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


def test_create_provider_accepts_anthropic_type(db_client, admin_client, db_engine, db_session):
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


# ---- T-19 GWT-07.6：伪装不熔断；探针走网关 chat 适配叶 ----
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.services import channel_probe_service as probe_mod
from backend.services.channel_probe_service import (
    DEFAULT_PROBE_QUESTIONS,
    ChannelProbeService,
)
from backend.services.newapi_api import RELAY_CHANNEL_CFG_PREFIX, RELAY_CHANNEL_STATE_PREFIX
from stubs import FakeRedis


def _probe_svc(redis=None) -> ChannelProbeService:
    svc = ChannelProbeService.__new__(ChannelProbeService)
    svc._running = False
    svc._loop_task = None
    svc._redis = redis if redis is not None else FakeRedis()
    return svc


def test_t19_probe_source_no_dsn_uses_gateway_chat():
    """探针走适配叶 /v1/chat/completions；无网关 DSN；阈值仍 0.15。"""
    root = Path(__file__).resolve().parents[2]
    probe_src = (root / "backend/services/channel_probe_service.py").read_text(encoding="utf-8")
    score_src = (root / "backend/services/channel_probe_score.py").read_text(encoding="utf-8")
    sched_src = (root / "backend/services/channel_scheduler_service.py").read_text(encoding="utf-8")
    assert "DB_DSN" not in probe_src
    assert "create_async_engine" not in probe_src
    assert "NewapiApiClient" not in probe_src
    assert "llm_gateway.chat" in probe_src
    assert "chat_completions" in probe_src
    assert "DB_DSN" not in sched_src
    assert "create_async_engine" not in sched_src
    assert "_USAGE_SQL" not in sched_src
    assert "LITELLM.DB_DSN" not in probe_src + sched_src
    assert "_REF_SIMILARITY_SPOOF_THRESHOLD = 0.15" in score_src


@pytest.mark.asyncio
async def test_gwt_07_6_spoofed_keeps_channel_usable_window_quota_unchanged():
    """GWT-07.6：spoofed 后渠道仍可用；不自动关闭；窗口与额度不变。"""
    redis = FakeRedis()
    cfg_key = f"{RELAY_CHANNEL_CFG_PREFIX}2"
    redis.hashes[cfg_key] = {
        "limit_quota": "500", "window_hours": "12", "cooldown_seconds": "1800",
    }
    snapshot = dict(redis.hashes[cfg_key])
    svc = _probe_svc(redis)
    recorded: list = []
    budget_calls: list = []

    async def _spoof_chat(body, **kwargs):
        return {
            "choices": [{"message": {"content": "我是 GLM-4"}}],
            "usage": {"total_tokens": 20},
            "model": body.get("model"),
        }

    async def _budget(*_a, **_k):
        budget_calls.append("budget")
        return {}

    svc._record_probe_result = AsyncMock(side_effect=lambda **kw: recorded.append(kw))
    with patch.object(probe_mod, "chat_completions", _spoof_chat), \
         patch.object(probe_mod.gw_admin, "create_budget", _budget), \
         patch.object(probe_mod.gw_admin, "update_budget", _budget), \
         patch.object(probe_mod.gw_admin, "update_model", _budget), \
         patch.object(probe_mod, "NotifyService") as notify_cls:
        notify_cls.return_value.notify_text = AsyncMock()
        await svc._probe_channel(
            {"gateway_ref": "2", "model_name": "gpt-4o", "name": "gpt-4o"},
            None, DEFAULT_PROBE_QUESTIONS, "batch-spoof",
        )
    assert recorded[0]["verdict"] == "spoofed"
    assert recorded[0]["channel_id"] == 2
    assert recorded[0]["scores"]["_gateway_ref"] == "2"
    assert redis.hashes[cfg_key] == snapshot
    assert budget_calls == []
    assert f"{RELAY_CHANNEL_STATE_PREFIX}2" not in redis.strings
    notify_cls.return_value.notify_text.assert_awaited()


@pytest.mark.asyncio
async def test_probe_collects_via_gateway_chat_completions_not_newapi():
    seen: list[dict] = []

    async def _chat(body, **kwargs):
        seen.append(body)
        return {
            "choices": [{"message": {"content": "我是 gpt-4o 模型"}}],
            "usage": {"total_tokens": 8},
            "model": body.get("model"),
        }

    svc = _probe_svc()
    with patch.object(probe_mod, "chat_completions", _chat):
        row = await svc._probe_chat("gpt-4o", "你是什么模型？请只回答你的模型名称。")
    assert row["ok"] is True
    assert seen[0]["model"] == "gpt-4o"
    assert seen[0]["stream"] is False
    assert seen[0]["messages"][0]["role"] == "user"
