"""new-api 管控 API 单测（admin 渠道健康页只读端点）

约定：不连真实 MySQL/new-api，TestClient 走 conftest 的 app fixture
（get_current_user 全局 override 为 admin）；分层打桩：
- NewapiApiClient：patch backend.services.newapi_overview_service.NewapiApiClient
- Repository：patch 类方法（AsyncMock，验证 skip/limit/channel_id 换算）
- settings：patch service 命名空间的 settings.get（开关/URL 用例）

覆盖：
- overview：正常聚合（字段映射 / key 敏感字段剔除 / 未知字段收 extra / 本地统计）
- overview：客户端异常降级 available=false（HTTP 200 不 500）
- overview：开关关闭 reason="newapi disabled"（不实例化客户端）；缺 id 条目跳过
- events / probe-results：分页换算（page/page_size → skip/limit）与渠道过滤
- 权限：operator 访问 403；参数校验 page<1 422
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.repositories.newapi_repository import (
    ChannelEventRepository,
    ChannelProbeResultRepository,
)
from stubs import fake_settings as _fake_settings  # 共享桩（唯一定义处见 stubs.py）

# overview 端点路径（v1 前缀）
OVERVIEW_URL = "/api/v1/newapi/overview"
EVENTS_URL = "/api/v1/newapi/events"
PROBE_RESULTS_URL = "/api/v1/newapi/probe-results"

# 测试用远端渠道原始 dict（含敏感字段 key 与未知字段，验证宽松映射契约）
_RAW_CHANNEL = {
    "id": 5, "name": "prov-a", "status": 1, "type": 1,
    "used_quota": 1500, "balance": 9.5, "response_time": 320,
    "test_time": 1756500000, "models": "gpt-4o,gpt-4o-mini", "group": "default",
    "base_url": "https://upstream.test/v1", "priority": 0, "weight": 0,
    "created_time": 1756000000,
    "key": "sk-secret-should-not-leak",
    "unknown_field": "keep-me",
}

_ENABLED_SETTINGS = {"NEWAPI.ENABLED": True, "NEWAPI.BASE_URL": "http://newapi.test"}


class _FakeClient:
    """NewapiApiClient 桩（list_channels 可预设返回或异常）"""

    def __init__(self, channels=None, error: Exception | None = None, **kwargs):
        self.kwargs = kwargs
        self._channels = channels or []
        self._error = error

    async def list_channels(self):
        if self._error is not None:
            raise self._error
        return self._channels


@pytest.fixture
def api_client(client, app):
    """client + get_async_db override（mock session，Repository 不落真库）"""
    from platform_core.db import get_async_db

    session = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    app.dependency_overrides[get_async_db] = lambda: session
    yield client
    app.dependency_overrides.pop(get_async_db, None)


# ---------------- overview：正常聚合 ----------------
class TestOverviewAggregation:
    def test_normal_aggregation_maps_and_strips_secrets(
        self, api_client, monkeypatch
    ):
        """正常聚合：字段映射 / key 剔除 / 未知字段收 extra / 本地统计附带"""
        monkeypatch.setattr(
            "backend.services.newapi_overview_service.NewapiApiClient",
            lambda **kw: _FakeClient(channels=[dict(_RAW_CHANNEL)], **kw),
        )
        monkeypatch.setattr(
            "backend.services.newapi_overview_service.settings",
            _fake_settings(**_ENABLED_SETTINGS),
        )
        monkeypatch.setattr(
            ChannelEventRepository, "count_events_since", AsyncMock(return_value=7)
        )
        monkeypatch.setattr(
            ChannelProbeResultRepository, "latest_batch_id",
            AsyncMock(return_value="batch-abc"),
        )
        monkeypatch.setattr(
            ChannelProbeResultRepository, "count_results_by_verdict",
            AsyncMock(return_value={"original": 3, "spoofed": 1, "offline": 1}),
        )
        resp = api_client.get(OVERVIEW_URL)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["available"] is True
        assert body["total"] == 1
        channel = body["channels"][0]
        assert channel["id"] == 5 and channel["name"] == "prov-a"
        assert channel["status"] == 1 and channel["type"] == 1
        assert channel["used_quota"] == 1500 and channel["balance"] == 9.5
        assert channel["response_time"] == 320
        assert channel["extra"] == {"unknown_field": "keep-me"}
        # 敏感字段绝不透传（整个响应体均不出现）
        assert "key" not in channel
        assert "sk-secret-should-not-leak" not in resp.text
        # 本地统计
        assert body["events_24h"] == 7
        assert body["latest_batch_id"] == "batch-abc"
        assert body["latest_batch_verdicts"] == {"original": 3, "spoofed": 1, "offline": 1}

    def test_minimal_channel_loose_mapping(self, api_client, monkeypatch):
        """宽松映射：仅含 id 的渠道条目也能映射（缺失字段取默认值，extra 为空）"""
        monkeypatch.setattr(
            "backend.services.newapi_overview_service.NewapiApiClient",
            lambda **kw: _FakeClient(channels=[{"id": 9}], **kw),
        )
        monkeypatch.setattr(
            "backend.services.newapi_overview_service.settings",
            _fake_settings(**_ENABLED_SETTINGS),
        )
        monkeypatch.setattr(
            ChannelEventRepository, "count_events_since", AsyncMock(return_value=0)
        )
        monkeypatch.setattr(
            ChannelProbeResultRepository, "latest_batch_id", AsyncMock(return_value=None)
        )
        resp = api_client.get(OVERVIEW_URL)
        assert resp.status_code == 200
        body = resp.json()["data"]
        channel = body["channels"][0]
        assert channel["id"] == 9 and channel["name"] == ""
        assert channel["status"] == 0 and channel["extra"] == {}
        assert body["latest_batch_id"] is None
        assert body["latest_batch_verdicts"] == {}

    def test_skips_entry_without_id(self, api_client, monkeypatch):
        """缺 id 的条目跳过（宽松容错，不因单条脏数据 500）"""
        monkeypatch.setattr(
            "backend.services.newapi_overview_service.NewapiApiClient",
            lambda **kw: _FakeClient(channels=[{"name": "no-id"}, dict(_RAW_CHANNEL)], **kw),
        )
        monkeypatch.setattr(
            "backend.services.newapi_overview_service.settings",
            _fake_settings(**_ENABLED_SETTINGS),
        )
        monkeypatch.setattr(
            ChannelEventRepository, "count_events_since", AsyncMock(return_value=0)
        )
        monkeypatch.setattr(
            ChannelProbeResultRepository, "latest_batch_id", AsyncMock(return_value=None)
        )
        resp = api_client.get(OVERVIEW_URL)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["available"] is True
        assert [c["id"] for c in body["channels"]] == [5]
        assert body["total"] == 1

    def test_no_probe_batch_skips_verdict_query(self, api_client, monkeypatch):
        """无探针记录时 verdict 分布为空 dict（不触发分布查询）"""
        monkeypatch.setattr(
            "backend.services.newapi_overview_service.NewapiApiClient",
            lambda **kw: _FakeClient(channels=[], **kw),
        )
        monkeypatch.setattr(
            "backend.services.newapi_overview_service.settings",
            _fake_settings(**_ENABLED_SETTINGS),
        )
        monkeypatch.setattr(
            ChannelEventRepository, "count_events_since", AsyncMock(return_value=2)
        )
        verdict_mock = AsyncMock(return_value={})
        monkeypatch.setattr(
            ChannelProbeResultRepository, "latest_batch_id", AsyncMock(return_value=None)
        )
        monkeypatch.setattr(
            ChannelProbeResultRepository, "count_results_by_verdict", verdict_mock
        )
        resp = api_client.get(OVERVIEW_URL)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["events_24h"] == 2
        assert body["latest_batch_verdicts"] == {}
        verdict_mock.assert_not_awaited()


# ---------------- overview：降级路径 ----------------
class TestOverviewDegradation:
    def test_client_exception_degrades_200(self, api_client, monkeypatch):
        """客户端异常 → HTTP 200 + available=false + reason（降级不 500）"""
        monkeypatch.setattr(
            "backend.services.newapi_overview_service.NewapiApiClient",
            lambda **kw: _FakeClient(error=RuntimeError("boom"), **kw),
        )
        monkeypatch.setattr(
            "backend.services.newapi_overview_service.settings",
            _fake_settings(**_ENABLED_SETTINGS),
        )
        monkeypatch.setattr(
            ChannelEventRepository, "count_events_since", AsyncMock(return_value=1)
        )
        monkeypatch.setattr(
            ChannelProbeResultRepository, "latest_batch_id", AsyncMock(return_value=None)
        )
        resp = api_client.get(OVERVIEW_URL)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["available"] is False
        assert "unreachable" in body["reason"]
        assert body["channels"] == [] and body["total"] == 0
        # 本地统计不随远程降级丢失
        assert body["events_24h"] == 1

    def test_timeout_degrades(self, api_client, monkeypatch):
        """拉取超时（wait_for 到期）→ 降级 available=false"""
        import asyncio

        async def _hang(**kwargs):
            await asyncio.sleep(10)

        monkeypatch.setattr(
            "backend.services.newapi_overview_service.OVERVIEW_TIMEOUT_SECONDS", 0.01
        )
        monkeypatch.setattr(
            "backend.services.newapi_overview_service.NewapiApiClient",
            lambda **kw: SimpleNamespace(list_channels=_hang, **kw),
        )
        monkeypatch.setattr(
            "backend.services.newapi_overview_service.settings",
            _fake_settings(**_ENABLED_SETTINGS),
        )
        monkeypatch.setattr(
            ChannelEventRepository, "count_events_since", AsyncMock(return_value=0)
        )
        monkeypatch.setattr(
            ChannelProbeResultRepository, "latest_batch_id", AsyncMock(return_value=None)
        )
        resp = api_client.get(OVERVIEW_URL)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["available"] is False
        assert "unreachable" in body["reason"]

    def test_disabled_switch_never_instantiates_client(self, api_client, monkeypatch):
        """开关关闭 → available=false + reason="newapi disabled"，且不发起远程调用"""
        client_spy = MagicMock(side_effect=AssertionError("不应实例化客户端"))
        monkeypatch.setattr(
            "backend.services.newapi_overview_service.NewapiApiClient", client_spy
        )
        monkeypatch.setattr(
            "backend.services.newapi_overview_service.settings",
            _fake_settings(**{"NEWAPI.ENABLED": False}),
        )
        monkeypatch.setattr(
            ChannelEventRepository, "count_events_since", AsyncMock(return_value=0)
        )
        monkeypatch.setattr(
            ChannelProbeResultRepository, "latest_batch_id", AsyncMock(return_value=None)
        )
        resp = api_client.get(OVERVIEW_URL)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["available"] is False
        assert body["reason"] == "newapi disabled"
        client_spy.assert_not_called()


# ---------------- events / probe-results 分页 ----------------
def _event_stub(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=11, channel_id=7, action="disabled", usage=1500, limit_quota=1000,
        window_hours=24, reason="超限", source="scheduler",
        created_at=datetime(2026, 8, 30, 12, 0, 0),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _probe_stub(**overrides) -> SimpleNamespace:
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
        """page/page_size → skip/limit 换算 + channel_id 透传；分页信封 data.items"""
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
        assert body["items"][0]["action"] == "disabled"
        assert body["items"][0]["source"] == "scheduler"

    def test_events_default_pagination_no_filter(self, api_client, monkeypatch):
        """缺省参数：page=1/page_size=20，channel_id 为 None"""
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
        """探针结果分页：verdict str→枚举 / scores dict 透传 / batch_id 保留"""
        list_mock = AsyncMock(return_value=[_probe_stub()])
        count_mock = AsyncMock(return_value=1)
        monkeypatch.setattr(ChannelProbeResultRepository, "list_results", list_mock)
        monkeypatch.setattr(ChannelProbeResultRepository, "count_results", count_mock)
        resp = api_client.get(PROBE_RESULTS_URL, params={"page": 2, "page_size": 10})
        assert resp.status_code == 200
        list_mock.assert_awaited_once_with(skip=10, limit=10, channel_id=None)
        body = resp.json()["data"]
        assert body["total"] == 1
        item = body["items"][0]
        assert item["verdict"] == "spoofed"
        assert item["model"] == "gpt-4o"
        assert item["batch_id"] == "batch-abc"
        assert item["scores"]["identity"] == 0.0
        assert item["latency_ms"] == 800

    def test_invalid_page_rejected(self, api_client, monkeypatch):
        """page<1 / page_size>100 参数校验 422"""
        monkeypatch.setattr(
            ChannelEventRepository, "list_events", AsyncMock(return_value=[])
        )
        monkeypatch.setattr(
            ChannelEventRepository, "count_events", AsyncMock(return_value=0)
        )
        assert api_client.get(EVENTS_URL, params={"page": 0}).status_code == 422
        assert api_client.get(EVENTS_URL, params={"page_size": 101}).status_code == 422


# ---------------- 权限与校验 ----------------
class TestPermissions:
    def test_overview_requires_admin(self, api_client, app):
        """operator 访问 overview → 403"""
        from backend.app.api.deps import CurrentUser as _CU, get_current_user

        async def _operator_user():
            return _CU(id=2, username="op", role="operator")

        async def _admin_user():
            return _CU(id=1, username="test-admin", role="admin")

        original = app.dependency_overrides[get_current_user]
        app.dependency_overrides[get_current_user] = _operator_user
        try:
            resp = api_client.get(OVERVIEW_URL)
        finally:
            app.dependency_overrides[get_current_user] = original
        assert resp.status_code == 403

    def test_events_and_probe_results_require_admin(self, api_client, app):
        """operator 访问 events / probe-results → 403"""
        from backend.app.api.deps import CurrentUser as _CU, get_current_user

        async def _operator_user():
            return _CU(id=2, username="op", role="operator")

        async def _admin_user():
            return _CU(id=1, username="test-admin", role="admin")

        original = app.dependency_overrides[get_current_user]
        app.dependency_overrides[get_current_user] = _operator_user
        try:
            assert api_client.get(EVENTS_URL).status_code == 403
            assert api_client.get(PROBE_RESULTS_URL).status_code == 403
        finally:
            app.dependency_overrides[get_current_user] = original


class TestWithPatch:
    def test_settings_patch_scope_is_service_module(self, monkeypatch):
        """settings 打桩限定在 service 命名空间（不污染其他模块的 settings）"""
        from backend.services import newapi_overview_service as svc_mod

        original = svc_mod.settings
        monkeypatch.setattr(
            svc_mod, "settings", _fake_settings(**{"NEWAPI.ENABLED": False})
        )
        assert svc_mod.settings.get("NEWAPI.ENABLED", True) is False
        assert original is not svc_mod.settings
