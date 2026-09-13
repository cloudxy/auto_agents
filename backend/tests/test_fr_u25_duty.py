"""T-26 FR-U25：值班三态 empty/degrade/live 互斥；租户 404 同形；伪装不关渠。"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.repositories.newapi_repository import (
    ChannelEventRepository,
    ChannelProbeResultRepository,
)
from backend.services.gateway_models import (
    DUTY_DEGRADE_71_3,
    DUTY_EMPTY_71_2,
    DUTY_PAGE_DEGRADE,
    DUTY_PAGE_EMPTY,
    DUTY_PAGE_LIVE,
    DUTY_ROW_LIVE,
    DUTY_ROW_LIVE_TEXT,
    apply_duty_row,
    map_gateway_model,
)
from backend.services.newapi_api import (
    RELAY_CHANNEL_CFG_PREFIX,
    RELAY_CHANNEL_STATE_PREFIX,
    _channel_id_from_ref,
)
from backend.services.newapi_overview_service import (
    EVENTS_WINDOW_HOURS,
    NewapiOverviewService,
    _ModelFetchResult,
)
from conftest import make_tenant_owner_headers

OVERVIEW = "/api/v1/newapi/overview"
EVENTS = "/api/v1/newapi/events"
PROBES = "/api/v1/newapi/probe-results"
CHANNELS = "/api/v1/newapi/channels"
PROBE = "/api/v1/newapi/probe"
GHOST = "/api/v1/admin/tenants"
SORRY = "抱歉您没有权限"
NO_CHANNELS = "暂无渠道"
BUYABLE = "当前可买"
DEGRADE_COPY_FRAGMENT = "LLM 网关管理面不可达"

_RAW_A = {
    "model_name": "gpt-4o",
    "litellm_params": {
        "model": "openai/gpt-4o",
        "api_base": "https://upstream.test/v1",
        "api_key": "sk-secret-should-not-leak",
    },
    "model_info": {"id": "dep-gpt-4o", "mode": "chat"},
}
_RAW_B = {
    "model_name": "claude-3",
    "litellm_params": {
        "model": "anthropic/claude-3",
        "api_base": "https://upstream.test/v1",
        "api_key": "sk-other-secret",
    },
    "model_info": {"id": "dep-claude", "mode": "chat"},
}


def _patch_gateway(monkeypatch, models=None, error: Exception | None = None):
    async def _list_models():
        if error is not None:
            raise error
        return {"data": models if models is not None else []}

    async def _list_deployments():
        return {"data": []}

    monkeypatch.setattr(
        "backend.services.newapi_overview_service.gw_admin.list_models",
        _list_models,
    )
    monkeypatch.setattr(
        "backend.services.newapi_overview_service.gw_admin.list_deployments",
        _list_deployments,
    )


def _local_stats(monkeypatch, events=0, batch_id=None, verdicts=None, latest=None):
    latest_mock = AsyncMock(return_value=latest or {})
    monkeypatch.setattr(
        ChannelEventRepository, "count_events_since", AsyncMock(return_value=events),
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
        ChannelProbeResultRepository, "latest_result_per_channel", latest_mock,
    )
    return latest_mock


def _probe_row(gateway_ref: str, model: str, verdict: str) -> tuple[int, object]:
    cid = _channel_id_from_ref(gateway_ref)
    row = SimpleNamespace(
        id=1, channel_id=cid, model=model, verdict=verdict,
        scores={"_gateway_ref": gateway_ref}, batch_id="batch-u25",
    )
    return cid, row


@pytest.fixture
def api_client(platform_admin_client, app):
    from platform_core.db import get_async_db

    session = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    app.dependency_overrides[get_async_db] = lambda: session
    yield platform_admin_client
    app.dependency_overrides.pop(get_async_db, None)


def _assert_no_banned(resp):
    assert NO_CHANNELS not in resp.text
    assert BUYABLE not in resp.text
    assert SORRY not in resp.text
    assert "sk-secret" not in resp.text


def test_gwt_u25_2_empty_reachable_zero_models(api_client, monkeypatch):
    """GWT-U25.2：可达且 0 模型 → 空态句；禁止「暂无渠道」；不是加载失败。"""
    _patch_gateway(monkeypatch, models=[])
    _local_stats(monkeypatch, events=4, batch_id="batch-local", verdicts={})
    resp = api_client.get(OVERVIEW)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["available"] is True
    assert body["total"] == 0
    assert body["models"] == []
    assert body["empty_state"] == DUTY_EMPTY_71_2 == "还没有平台模型，去网关登记"
    assert body["degrade_state"] is None
    assert body["duty_page_state"] == DUTY_PAGE_EMPTY
    assert body["events_24h"] == 4
    assert "加载失败" not in resp.text
    assert DEGRADE_COPY_FRAGMENT not in resp.text
    _assert_no_banned(resp)


def test_gwt_u25_4_degrade_unreachable_keeps_local(api_client, monkeypatch):
    """GWT-U25.4：管理面不可达 → 降级句；仍回本地事件/探针；禁止空态/暂无渠道。"""
    _patch_gateway(monkeypatch, error=RuntimeError("gateway down"))
    latest_mock = _local_stats(
        monkeypatch, events=9, batch_id="batch-local",
        verdicts={"original": 2, "spoofed": 1},
    )
    resp = api_client.get(OVERVIEW)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["available"] is False
    assert body["degrade_state"] == DUTY_DEGRADE_71_3
    assert body["degrade_state"] == "LLM 网关管理面不可达，仅本地事件/探针"
    assert body["empty_state"] is None
    assert body["duty_page_state"] == DUTY_PAGE_DEGRADE
    assert body["events_24h"] == 9
    assert body["latest_batch_id"] == "batch-local"
    assert body["models"] == []
    latest_mock.assert_not_awaited()
    assert "还没有平台模型，去网关登记" not in resp.text
    _assert_no_banned(resp)


def test_gwt_u25_4_degrade_nonempty_models_not_live(api_client, monkeypatch):
    """QA-03：降级响应若出现 model 行，不得 duty_row_status=live；本地 24h 仍回。"""
    mapped = map_gateway_model(dict(_RAW_A))
    assert mapped is not None
    live_row = apply_duty_row(mapped, "original")
    assert live_row.duty_row_status == DUTY_ROW_LIVE

    async def _fetch(_self):
        return _ModelFetchResult(False, DUTY_DEGRADE_71_3, [live_row], [])

    monkeypatch.setattr(NewapiOverviewService, "_fetch_models", _fetch)
    latest_mock = _local_stats(
        monkeypatch, events=9, batch_id="batch-local",
        verdicts={"original": 2},
    )
    resp = api_client.get(OVERVIEW)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["available"] is False
    assert body["duty_page_state"] == DUTY_PAGE_DEGRADE
    assert body["empty_state"] is None
    assert body["degrade_state"] == DUTY_DEGRADE_71_3
    assert body["models"], "non-empty degrade fixture required"
    assert all(m.get("duty_row_status") != DUTY_ROW_LIVE for m in body["models"])
    assert all(m.get("duty_row_status_text") != DUTY_ROW_LIVE_TEXT for m in body["models"])
    assert body["events_24h"] == 9
    latest_mock.assert_not_awaited()
    assert "还没有平台模型，去网关登记" not in resp.text
    _assert_no_banned(resp)


def test_gwt_u25_reachable_registered_no_original_not_empty(api_client, monkeypatch):
    """QA-04：可达 ∧ ≥1 模型 ∧ 无 original → 页态不是 empty/degrade；行不标活。"""
    cid_a, row_a = _probe_row("dep-gpt-4o", "gpt-4o", "spoofed")
    _patch_gateway(monkeypatch, models=[dict(_RAW_A), dict(_RAW_B)])
    _local_stats(
        monkeypatch, events=2, batch_id="batch-none",
        verdicts={"spoofed": 1}, latest={cid_a: row_a},
    )
    resp = api_client.get(OVERVIEW)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["available"] is True
    assert body["total"] >= 1
    assert body["models"]
    assert body["empty_state"] is None
    assert body["degrade_state"] is None
    assert body["duty_page_state"] not in {DUTY_PAGE_EMPTY, DUTY_PAGE_DEGRADE}
    assert body["duty_page_state"] is None
    assert all(m.get("duty_row_status") != DUTY_ROW_LIVE for m in body["models"])
    assert "还没有平台模型，去网关登记" not in resp.text
    assert DEGRADE_COPY_FRAGMENT not in resp.text
    _assert_no_banned(resp)


def test_overview_latest_probe_scoped_to_current_gateway_refs(api_client, monkeypatch):
    """QA-05：值班总览按当前 gateway_ref 集合 + 回看窗拉最新探针，不扫全表。"""
    cid_a, row_a = _probe_row("dep-gpt-4o", "gpt-4o", "original")
    _patch_gateway(monkeypatch, models=[dict(_RAW_A)])
    latest_mock = _local_stats(
        monkeypatch, events=1, batch_id="batch-u25",
        latest={cid_a: row_a},
    )
    before = datetime.now()
    resp = api_client.get(OVERVIEW)
    after = datetime.now()
    assert resp.status_code == 200
    latest_mock.assert_awaited()
    kwargs = latest_mock.await_args.kwargs
    ids = kwargs.get("channel_ids")
    assert ids is not None and cid_a in ids
    assert set(ids) == {cid_a}
    since = kwargs.get("since")
    assert since is not None
    assert EVENTS_WINDOW_HOURS == 24
    lo = before - timedelta(hours=EVENTS_WINDOW_HOURS)
    hi = after - timedelta(hours=EVENTS_WINDOW_HOURS)
    assert lo <= since <= hi


@pytest.mark.asyncio
async def test_latest_result_per_channel_without_ids_does_not_scan():
    """QA-05：无当前渠道集合时不得执行全表 GROUP BY。"""
    session = MagicMock()
    stub = MagicMock()
    stub.scalars.return_value.all.return_value = [SimpleNamespace(channel_id=1)]
    session.execute = AsyncMock(return_value=stub)
    repo = ChannelProbeResultRepository(session)
    out = await repo.latest_result_per_channel()
    assert out == {}
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_latest_result_per_channel_sql_bounded_to_ids_and_since():
    """QA-05：SQL 必须带 channel_id IN 与 created_at 回看窗。"""
    session = MagicMock()
    stub = MagicMock()
    stub.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=stub)
    repo = ChannelProbeResultRepository(session)
    since = datetime(2026, 9, 1, 12, 0, 0)
    out = await repo.latest_result_per_channel(channel_ids=[42, 99], since=since)
    assert out == {}
    session.execute.assert_awaited_once()
    compiled = str(session.execute.call_args.args[0].compile(
        compile_kwargs={"literal_binds": True},
    ))
    assert "channel_probe_results" in compiled
    assert "42" in compiled and "99" in compiled
    assert "channel_id" in compiled.lower() or "channel_id" in compiled
    assert "2026-09-01" in compiled
    assert "created_at" in compiled
    assert "LIMIT" in compiled.upper()


def test_gwt_u25_1_live_row_not_empty_or_degrade(api_client, monkeypatch):
    """GWT-U25.1：可达、已登记、探针 original → 该行「活」；页级不得空/降级句。"""
    cid_a, row_a = _probe_row("dep-gpt-4o", "gpt-4o", "original")
    cid_b, row_b = _probe_row("dep-claude", "claude-3", "spoofed")
    _patch_gateway(monkeypatch, models=[dict(_RAW_A), dict(_RAW_B)])
    _local_stats(
        monkeypatch, events=1, batch_id="batch-u25",
        verdicts={"original": 1, "spoofed": 1},
        latest={cid_a: row_a, cid_b: row_b},
    )
    resp = api_client.get(OVERVIEW)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["available"] is True
    assert body["total"] == 2
    assert body["empty_state"] is None
    assert body["degrade_state"] is None
    assert body["duty_page_state"] == DUTY_PAGE_LIVE
    by_ref = {m["gateway_ref"]: m for m in body["models"]}
    live = by_ref["dep-gpt-4o"]
    spoof = by_ref["dep-claude"]
    assert live["duty_row_status"] == DUTY_ROW_LIVE
    assert live["duty_row_status_text"] == DUTY_ROW_LIVE_TEXT == "活"
    assert spoof["duty_row_status"] == "spoofed"
    assert spoof["duty_row_status_text"] is None
    assert "还没有平台模型，去网关登记" not in resp.text
    assert DEGRADE_COPY_FRAGMENT not in resp.text
    _assert_no_banned(resp)


def test_gwt_u25_3_tenant_company_admin_duty_apis_404(db_client, db_session):
    """GWT-U25.3：租户公司管理员打值班 API = 404 同形（无列表/密钥/抱歉）。"""
    owner, _tid = make_tenant_owner_headers(db_session, slug="u25-duty")
    ghost = db_client.get(GHOST, headers=owner)
    assert ghost.status_code == 404
    paths = (OVERVIEW, EVENTS, PROBES, CHANNELS)
    for path in paths:
        resp = db_client.get(path, headers=owner)
        assert resp.status_code == ghost.status_code == 404, path
        body, other = resp.json(), ghost.json()
        assert body["code"] == other["code"] == "HTTP_404"
        assert body["message"] == other["message"] == "Not Found"
        assert "FORBIDDEN" not in resp.text
        assert SORRY not in resp.text
        assert "channels" not in (body.get("data") or {})
        assert "sk-" not in resp.text.lower()
        _assert_no_banned(resp)
    posted = db_client.post(PROBE, headers=owner, json={"gateway_ref": "dep-gpt-4o"})
    assert posted.status_code == 404
    assert posted.json()["code"] == "HTTP_404"
    assert SORRY not in posted.text


@pytest.mark.asyncio
async def test_gwt_u25_spoofed_does_not_auto_disable_channel():
    """GWT-07.6 / U25：伪装只落库+通知，不关渠道、不改窗口/额度。"""
    from backend.services import channel_probe_service as probe_mod
    from backend.services.channel_probe_service import (
        DEFAULT_PROBE_QUESTIONS,
        ChannelProbeService,
    )
    from stubs import FakeRedis

    redis = FakeRedis()
    cfg_key = f"{RELAY_CHANNEL_CFG_PREFIX}2"
    redis.hashes[cfg_key] = {
        "limit_quota": "500", "window_hours": "12", "cooldown_seconds": "1800",
    }
    snapshot = dict(redis.hashes[cfg_key])
    svc = ChannelProbeService.__new__(ChannelProbeService)
    svc._running = False
    svc._loop_task = None
    svc._redis = redis
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
    assert redis.hashes[cfg_key] == snapshot
    assert budget_calls == []
    assert f"{RELAY_CHANNEL_STATE_PREFIX}2" not in redis.strings
    notify_cls.return_value.notify_text.assert_awaited()
