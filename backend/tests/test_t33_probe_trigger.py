"""T-33 立即探测手动入口（GWT-98.4 / 98.7）：POST /newapi/probe

- 超管触发：accepted + manual- 批次 id，触发即返回（不阻塞轮询循环）
- 目标不在网关列表：accepted=false + 中文原因（200，不 500）
- 非平台超管：404 同形且零渠道/事件副作用（守卫先于 handler）
- 服务面：引擎复用（_probe_channel ref_results=None）+ 同渠道在飞复用批次

不连真实 MySQL/LiteLLM：TestClient 走 conftest 的 app fixture；探针引擎 mock。
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.channel_probe_service import ChannelProbeService

PROBE_URL = "/api/v1/newapi/probe"


@pytest.fixture
def api_client(platform_admin_client, app):
    """平台超管特权 client + get_async_db override（mock session，record_audit 可用）"""
    from platform_core.db import get_async_db

    session = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    app.dependency_overrides[get_async_db] = lambda: session
    yield platform_admin_client
    app.dependency_overrides.pop(get_async_db, None)


class TestProbeTriggerPermissions:
    def test_operator_trigger_is_404_shape_without_side_effects(self, api_client, app, monkeypatch):
        """GWT-98.7：operator 触发立即探测 → 404 同形；引擎未被调用（零副作用）"""
        from backend.app.api.deps import CurrentUser as _CU, get_current_user

        trigger = AsyncMock()
        monkeypatch.setattr(ChannelProbeService, "trigger_manual_probe", trigger)

        async def _operator_user():
            return _CU(id=2, username="op", role="operator")

        original = app.dependency_overrides[get_current_user]
        app.dependency_overrides[get_current_user] = _operator_user
        try:
            resp = api_client.post(PROBE_URL, json={"gateway_ref": "dep-gpt-4o"})
        finally:
            app.dependency_overrides[get_current_user] = original
        assert resp.status_code == 404
        assert resp.json()["code"] == "HTTP_404"
        trigger.assert_not_awaited()


class TestProbeTriggerApi:
    def test_platform_admin_trigger_returns_accepted_batch(self, api_client, monkeypatch):
        """GWT-98.4：超管触发 → accepted=true + manual- 批次 id（触发即返回）"""
        monkeypatch.setattr(
            ChannelProbeService, "trigger_manual_probe",
            AsyncMock(return_value=(True, "manual-abc123", None)),
        )
        resp = api_client.post(PROBE_URL, json={"gateway_ref": "dep-gpt-4o"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["accepted"] is True
        assert data["batch_id"].startswith("manual-")
        assert data["gateway_ref"] == "dep-gpt-4o"
        assert data["reason"] is None

    def test_target_missing_returns_not_accepted_with_reason(self, api_client, monkeypatch):
        """目标不在网关列表（网关不可达同路径）→ accepted=false + 中文原因，不 500"""
        async def _empty_models(_self):
            return []

        monkeypatch.setattr(ChannelProbeService, "_list_mapped", _empty_models)
        resp = api_client.post(PROBE_URL, json={"gateway_ref": "dep-missing"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["accepted"] is False
        assert data["batch_id"] == ""
        assert data["reason"]

    def test_blank_ref_rejected_by_schema(self, api_client, monkeypatch):
        """空 gateway_ref 被 Schema 拒绝（422，不进 handler）"""
        monkeypatch.setattr(
            ChannelProbeService, "trigger_manual_probe",
            AsyncMock(return_value=(True, "manual-x", None)),
        )
        resp = api_client.post(PROBE_URL, json={"gateway_ref": ""})
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_trigger_manual_probe_reuses_engine_and_inflight_batch(monkeypatch):
    """服务面：受理后后台单渠道探测（ref_results=None 口径）+ 在飞复用同一批次"""
    async def _models(_self):
        return [{"gateway_ref": "dep-a", "model_name": "gpt-4o", "name": "gpt-4o"}]

    probed = AsyncMock()
    monkeypatch.setattr(ChannelProbeService, "_list_mapped", _models)
    monkeypatch.setattr(ChannelProbeService, "_probe_channel", probed)

    service = ChannelProbeService()
    accepted, batch_id, reason = await service.trigger_manual_probe("dep-a")
    assert accepted is True
    assert reason is None
    assert batch_id.startswith("manual-")

    # 同渠道在飞 → 复用同一批次 id，不重复 spawn
    accepted_again, batch_again, _ = await service.trigger_manual_probe("dep-a")
    assert accepted_again is True
    assert batch_again == batch_id

    # 后台任务执行（事件循环让步后完成）：引擎复用、无参考口径
    for _ in range(4):
        await asyncio.sleep(0)
    probed.assert_awaited_once()
    target, ref_results, _questions, out_batch = probed.await_args.args
    assert target["gateway_ref"] == "dep-a"
    assert ref_results is None
    assert out_batch == batch_id


@pytest.mark.asyncio
async def test_trigger_manual_probe_blank_ref_short_circuits(monkeypatch):
    """空白 gateway_ref：先于任何网关 IO 拒绝（不触发 _list_mapped）"""
    listed = AsyncMock()
    monkeypatch.setattr(ChannelProbeService, "_list_mapped", listed)
    accepted, batch_id, reason = await ChannelProbeService().trigger_manual_probe("  ")
    assert accepted is False
    assert batch_id == ""
    assert reason
    listed.assert_not_awaited()
