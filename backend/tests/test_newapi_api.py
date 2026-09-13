"""值班管控 API 单测（T-18：网关模型列表 + 71.2/71.3 + GWT-70.3）

约定：不连真实 MySQL/LiteLLM，TestClient 走 conftest 的 app fixture。
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.repositories.newapi_repository import (
    ChannelEventRepository,
    ChannelProbeResultRepository,
)
from backend.services.gateway_models import DUTY_DEGRADE_71_3, DUTY_EMPTY_71_2

OVERVIEW_URL = "/api/v1/newapi/overview"
EVENTS_URL = "/api/v1/newapi/events"
PROBE_RESULTS_URL = "/api/v1/newapi/probe-results"
MODELS_URL = "/api/v1/newapi/models"
UPSTREAMS_URL = "/api/v1/newapi/upstreams"

_RAW_MODEL = {
    "model_name": "gpt-4o",
    "litellm_params": {
        "model": "openai/gpt-4o",
        "api_base": "https://upstream.test/v1",
        "api_key": "sk-secret-should-not-leak",
    },
    "model_info": {"id": "dep-gpt-4o", "mode": "chat"},
    "unknown_field": "keep-me",
}


def _patch_gateway(monkeypatch, models=None, error: Exception | None = None,
                   deployments=None):
    async def _list_models():
        if error is not None:
            raise error
        return {"data": models if models is not None else []}

    async def _list_deployments():
        return {"data": deployments if deployments is not None else []}

    monkeypatch.setattr(
        "backend.services.newapi_overview_service.gw_admin.list_models",
        _list_models,
    )
    monkeypatch.setattr(
        "backend.services.newapi_overview_service.gw_admin.list_deployments",
        _list_deployments,
    )


@pytest.fixture
def api_client(platform_admin_client, app):
    """平台超管特权 client + get_async_db override（mock session）"""
    from platform_core.db import get_async_db

    session = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    app.dependency_overrides[get_async_db] = lambda: session
    yield platform_admin_client
    app.dependency_overrides.pop(get_async_db, None)


def _local_stats(monkeypatch, events=0, batch_id=None, verdicts=None, latest=None):
    monkeypatch.setattr(
        ChannelEventRepository, "count_events_since", AsyncMock(return_value=events)
    )
    monkeypatch.setattr(
        ChannelProbeResultRepository, "latest_batch_id",
        AsyncMock(return_value=batch_id),
    )
    monkeypatch.setattr(
        ChannelProbeResultRepository, "count_results_by_verdict",
        AsyncMock(return_value=verdicts or {}),
    )
    monkeypatch.setattr(
        ChannelProbeResultRepository, "latest_result_per_channel",
        AsyncMock(return_value=latest or {}),
    )


class TestOverviewAggregation:
    def test_normal_aggregation_maps_and_strips_secrets(self, api_client, monkeypatch):
        """GWT-71.1：模型/部署列表；无完整上游 Key"""
        _patch_gateway(monkeypatch, models=[dict(_RAW_MODEL)], deployments=[dict(_RAW_MODEL)])
        _local_stats(
            monkeypatch, events=7, batch_id="batch-abc",
            verdicts={"original": 3, "spoofed": 1, "offline": 1},
        )
        resp = api_client.get(OVERVIEW_URL)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["available"] is True
        assert body["total"] == 1
        model = body["models"][0]
        assert model["gateway_ref"] == "dep-gpt-4o"
        assert model["model_name"] == "gpt-4o"
        assert model["api_base"] == "https://upstream.test/v1"
        assert model["api_key_masked"] != "sk-secret-should-not-leak"
        assert "sk-secret-should-not-leak" not in resp.text
        assert "key" not in model
        assert model["extra"] == {"unknown_field": "keep-me"}
        assert body["events_24h"] == 7
        assert body["latest_batch_id"] == "batch-abc"
        assert body["latest_batch_verdicts"] == {"original": 3, "spoofed": 1, "offline": 1}
        assert body["channels"] == []
        assert "暂无渠道" not in resp.text

    def test_empty_models_is_71_2_not_load_failure(self, api_client, monkeypatch):
        """GWT-71.2：可达且 0 模型 → 空态句；不是加载失败；禁止「暂无渠道」"""
        _patch_gateway(monkeypatch, models=[])
        _local_stats(monkeypatch, events=2)
        resp = api_client.get(OVERVIEW_URL)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["available"] is True
        assert body["total"] == 0
        assert body["models"] == []
        assert body["empty_state"] == DUTY_EMPTY_71_2
        assert body["empty_state"] == "还没有平台模型，去网关登记"
        assert body["degrade_state"] is None
        assert body["duty_page_state"] == "empty"
        assert body["events_24h"] == 2
        assert "暂无渠道" not in resp.text
        assert "加载失败" not in resp.text

    def test_skips_entry_without_name(self, api_client, monkeypatch):
        _patch_gateway(
            monkeypatch,
            models=[{"litellm_params": {}}, dict(_RAW_MODEL)],
        )
        _local_stats(monkeypatch)
        resp = api_client.get(OVERVIEW_URL)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["available"] is True
        assert [m["model_name"] for m in body["models"]] == ["gpt-4o"]
        assert body["total"] == 1

    def test_no_probe_batch_skips_verdict_query(self, api_client, monkeypatch):
        _patch_gateway(monkeypatch, models=[])
        _local_stats(monkeypatch, events=2, batch_id=None)
        verdict_mock = AsyncMock(return_value={})
        monkeypatch.setattr(
            ChannelProbeResultRepository, "count_results_by_verdict", verdict_mock
        )
        resp = api_client.get(OVERVIEW_URL)
        assert resp.status_code == 200
        assert resp.json()["data"]["latest_batch_verdicts"] == {}
        verdict_mock.assert_not_awaited()


class TestOverviewDegradation:
    def test_client_exception_degrades_200(self, api_client, monkeypatch):
        """GWT-71.3：不可达 → HTTP 200 + available=false + 冻结句；本地仍可见"""
        _patch_gateway(monkeypatch, error=RuntimeError("boom"))
        _local_stats(monkeypatch, events=1, batch_id="batch-local")
        resp = api_client.get(OVERVIEW_URL)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["available"] is False
        assert body["degrade_state"] == DUTY_DEGRADE_71_3
        assert body["degrade_state"] == "LLM 网关管理面不可达，仅本地事件/探针"
        assert body["reason"] == DUTY_DEGRADE_71_3
        assert body["duty_page_state"] == "degrade"
        assert body["empty_state"] is None
        assert body["models"] == [] and body["total"] == 0
        assert body["events_24h"] == 1
        assert body["latest_batch_id"] == "batch-local"
        assert "暂无渠道" not in resp.text

    def test_timeout_degrades(self, api_client, monkeypatch):
        import asyncio

        async def _hang():
            await asyncio.sleep(10)

        monkeypatch.setattr(
            "backend.services.newapi_overview_service.OVERVIEW_TIMEOUT_SECONDS", 0.01
        )
        monkeypatch.setattr(
            "backend.services.newapi_overview_service.gw_admin.list_models", _hang,
        )
        _local_stats(monkeypatch)
        resp = api_client.get(OVERVIEW_URL)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["available"] is False
        assert body["degrade_state"] == DUTY_DEGRADE_71_3


def _event_stub(**overrides) -> object:
    from types import SimpleNamespace
    defaults = dict(
        id=11, channel_id=7, action="disabled", usage=1500, limit_quota=1000,
        window_hours=24, reason="超限", source="scheduler",
        created_at=datetime(2026, 8, 30, 12, 0, 0),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _probe_stub(**overrides) -> object:
    from types import SimpleNamespace
    defaults = dict(
        id=21, channel_id=7, model="gpt-4o", verdict="spoofed",
        scores={"identity": 0.0, "total_calls": 9, "ok_calls": 9},
        latency_ms=800, batch_id="batch-abc",
        created_at=datetime(2026, 8, 30, 12, 0, 0),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestPagination:
    def test_events_pagination_and_filter(self, api_client, monkeypatch):
        list_mock = AsyncMock(return_value=[_event_stub()])
        count_mock = AsyncMock(return_value=23)
        monkeypatch.setattr(ChannelEventRepository, "list_events", list_mock)
        monkeypatch.setattr(ChannelEventRepository, "count_events", count_mock)
        resp = api_client.get(EVENTS_URL, params={"page": 3, "page_size": 5, "channel_id": 7})
        assert resp.status_code == 200
        list_mock.assert_awaited_once_with(skip=10, limit=5, channel_id=7)
        count_mock.assert_awaited_once_with(channel_id=7)
        body = resp.json()["data"]
        assert body["total"] == 23
        assert body["items"][0]["id"] == 11

    def test_events_default_pagination_no_filter(self, api_client, monkeypatch):
        list_mock = AsyncMock(return_value=[])
        count_mock = AsyncMock(return_value=0)
        monkeypatch.setattr(ChannelEventRepository, "list_events", list_mock)
        monkeypatch.setattr(ChannelEventRepository, "count_events", count_mock)
        resp = api_client.get(EVENTS_URL)
        assert resp.status_code == 200
        list_mock.assert_awaited_once_with(skip=0, limit=20, channel_id=None)
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == {"total": 0, "items": [], "page": 1, "page_size": 20,
                                "total_pages": 0}

    def test_probe_results_pagination_and_verdict_enum(self, api_client, monkeypatch):
        list_mock = AsyncMock(return_value=[_probe_stub()])
        count_mock = AsyncMock(return_value=1)
        monkeypatch.setattr(ChannelProbeResultRepository, "list_results", list_mock)
        monkeypatch.setattr(ChannelProbeResultRepository, "count_results", count_mock)
        resp = api_client.get(PROBE_RESULTS_URL, params={"page": 2, "page_size": 10})
        assert resp.status_code == 200
        list_mock.assert_awaited_once_with(skip=10, limit=10, channel_id=None)
        item = resp.json()["data"]["items"][0]
        assert item["verdict"] == "spoofed"
        assert item["model"] == "gpt-4o"

    def test_invalid_page_rejected(self, api_client, monkeypatch):
        monkeypatch.setattr(
            ChannelEventRepository, "list_events", AsyncMock(return_value=[])
        )
        monkeypatch.setattr(
            ChannelEventRepository, "count_events", AsyncMock(return_value=0)
        )
        assert api_client.get(EVENTS_URL, params={"page": 0}).status_code == 422
        assert api_client.get(EVENTS_URL, params={"page_size": 101}).status_code == 422


class TestPermissions:
    def test_overview_requires_platform_admin(self, api_client, app):
        """operator GET overview → 404 同形（GWT-71.4 / 07.3）"""
        from backend.app.api.deps import CurrentUser as _CU, get_current_user

        async def _operator_user():
            return _CU(id=2, username="op", role="operator")

        original = app.dependency_overrides[get_current_user]
        app.dependency_overrides[get_current_user] = _operator_user
        try:
            resp = api_client.get(OVERVIEW_URL)
        finally:
            app.dependency_overrides[get_current_user] = original
        assert resp.status_code == 404
        assert resp.json()["code"] == "HTTP_404"
        assert "sk-" not in resp.text.lower()

    def test_events_and_probe_results_require_platform_admin(self, api_client, app):
        from backend.app.api.deps import CurrentUser as _CU, get_current_user

        async def _operator_user():
            return _CU(id=2, username="op", role="operator")

        original = app.dependency_overrides[get_current_user]
        app.dependency_overrides[get_current_user] = _operator_user
        try:
            assert api_client.get(EVENTS_URL).status_code == 404
            assert api_client.get(PROBE_RESULTS_URL).status_code == 404
        finally:
            app.dependency_overrides[get_current_user] = original


def test_operator_or_tenant_admin_write_gateway_model_rejected_list_unchanged(
    api_client, app, monkeypatch,
):
    """GWT-70.3：租户 admin / operator 写平台网关模型或登记上游 → 拒绝；列表不变"""
    from backend.app.api.deps import CurrentUser as _CU, get_current_user

    create_spy = AsyncMock(return_value={"data": {"model_name": "hacked"}})
    monkeypatch.setattr(
        "backend.services.newapi_overview_service.gw_admin.create_model", create_spy,
    )
    _patch_gateway(monkeypatch, models=[dict(_RAW_MODEL)])
    _local_stats(monkeypatch, events=0)

    before = api_client.get(OVERVIEW_URL)
    assert before.status_code == 200
    before_models = before.json()["data"]["models"]
    assert len(before_models) == 1
    snapshot = [row["gateway_ref"] for row in before_models]

    model_body = {"model_name": "hacked", "litellm_params": {"model": "x"}}
    upstream_body = {
        "gateway_ref": "hack-up",
        "api_base": "https://evil.example/v1",
        "model_name": "hacked",
    }

    async def _operator():
        return _CU(id=2, username="op", role="operator", is_platform_admin=False)

    async def _tenant_admin():
        return _CU(id=3, username="boss", role="admin", is_platform_admin=False)

    original = app.dependency_overrides[get_current_user]
    try:
        for user_fn in (_operator, _tenant_admin):
            app.dependency_overrides[get_current_user] = user_fn
            m_resp = api_client.post(MODELS_URL, json=model_body)
            assert m_resp.status_code == 404, m_resp.text
            assert m_resp.json()["code"] == "HTTP_404"
            assert "抱歉" not in m_resp.text
            u_resp = api_client.post(UPSTREAMS_URL, json=upstream_body)
            assert u_resp.status_code == 404, u_resp.text
            assert u_resp.json()["code"] == "HTTP_404"
    finally:
        app.dependency_overrides[get_current_user] = original

    create_spy.assert_not_awaited()
    after = api_client.get(OVERVIEW_URL)
    assert after.status_code == 200
    after_models = after.json()["data"]["models"]
    assert [row["gateway_ref"] for row in after_models] == snapshot
    assert len(after_models) == len(before_models)
    assert "sk-secret-should-not-leak" not in after.text


def test_t18_config_prefix_no_third():
    """T-20：运行时只读 RELAY.* / LITELLM.*；禁止 NEWAPI.* settings 读；禁止第三前缀"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    files = [
        root / "backend/services/channel_config_service.py",
        root / "backend/services/newapi_overview_service.py",
        root / "backend/services/gateway_models.py",
        root / "backend/app/api/v1/newapi.py",
        root / "backend/services/newapi_api.py",
        root / "backend/services/channel_scheduler_service.py",
        root / "backend/services/channel_probe_service.py",
        root / "backend/app/__init__.py",
    ]
    needles = ('settings.get("NEWAPI.', "settings.get('NEWAPI.")
    for path in files:
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            assert needle not in text, path
        assert "GATEWAY." not in text
        assert "PROXY." not in text
        assert 'settings.set("' not in text
        if "hset" in text or "write_cfg_hash" in text:
            if path.name in {"channel_config_service.py", "newapi_api.py"}:
                assert "relay:channel:cfg:" in text or "RELAY_CHANNEL_CFG_PREFIX" in text
