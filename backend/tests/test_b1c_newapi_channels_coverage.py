"""B1c newapi/channels 配置面（T-18：网关模型列表 + Redis expand 双读）

覆盖：
- GET    /api/v1/newapi/channels
- PUT    /api/v1/newapi/channels/{channel_id}/config  （int 路径，类型不改）
- DELETE /api/v1/newapi/channels/{channel_id}/config
- PUT    /api/v1/newapi/models/{gateway_ref}/config

GET 非超管 404 同形；写面 require_platform_admin_or_404 → 404 同形（FR-U12）。
远端不可达 GET 200 空列表（不 502）。新写 relay:channel:cfg:{ref}。
"""
from unittest.mock import AsyncMock

import pytest

import backend.services.channel_config_service as cfg_mod
from backend.services.newapi_api import (
    NEWAPI_CHANNEL_CFG_PREFIX,
    RELAY_CHANNEL_CFG_PREFIX,
)
from stubs import FakeRedis, fake_settings

CHANNELS_URL = "/api/v1/newapi/channels"
MODELS_CFG_URL = "/api/v1/newapi/models"
OLD_KEY = f"{NEWAPI_CHANNEL_CFG_PREFIX}3"
RELAY_KEY_3 = f"{RELAY_CHANNEL_CFG_PREFIX}3"
RELAY_KEY_GPT = f"{RELAY_CHANNEL_CFG_PREFIX}gpt-4o"

_SETTINGS_DEFAULTS = {
    "RELAY.DEFAULT_WINDOW_QUOTA": 0,
    "RELAY.DEFAULT_WINDOW_HOURS": 24,
    "RELAY.DEFAULT_COOLDOWN_SECONDS": 3600,
}

_MODEL_3 = {
    "model_name": "m3",
    "model_info": {"id": "3", "mode": "chat"},
    "litellm_params": {"api_base": "https://a.example/v1", "api_key": "sk-secret-leak"},
}
_MODEL_GPT = {
    "model_name": "gpt-4o",
    "model_info": {"id": "gpt-4o", "mode": "chat"},
    "litellm_params": {"api_base": "https://b.example/v1"},
}


@pytest.fixture
def fake_redis():
    return FakeRedis()


def _wire(monkeypatch, redis: FakeRedis, models=None, list_error=None):
    async def _list_models():
        if list_error is not None:
            raise list_error
        return {"data": models if models is not None else [_MODEL_3]}

    monkeypatch.setattr(cfg_mod, "get_async_redis", lambda: redis)
    monkeypatch.setattr(cfg_mod.gw_admin, "list_models", _list_models)
    monkeypatch.setattr(cfg_mod, "settings", fake_settings(**_SETTINGS_DEFAULTS))


def test_channels_admin_ok_merged_view(platform_admin_client, monkeypatch, fake_redis):
    """合并视图：relay 配置 effective_source=channel；无配置未纳管"""
    fake_redis.hashes[RELAY_KEY_GPT] = {
        "limit_quota": "500", "window_hours": "12", "cooldown_seconds": "1800",
    }
    _wire(monkeypatch, fake_redis, models=[_MODEL_GPT, _MODEL_3])

    resp = platform_admin_client.get(CHANNELS_URL)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "SUCCESS"
    by_ref = {row["gateway_ref"]: row for row in body["data"]}
    assert set(by_ref) == {"gpt-4o", "3"}
    assert by_ref["gpt-4o"]["effective_source"] == "channel"
    assert by_ref["gpt-4o"]["config"]["limit_quota"] == 500
    assert by_ref["3"]["config"] is None
    assert by_ref["3"]["effective_source"] == "none"
    assert "sk-secret-leak" not in resp.text
    assert by_ref["3"].get("api_key_masked") != "sk-secret-leak"


def test_channels_dual_read_old_key_then_relay(
    platform_admin_client, monkeypatch, fake_redis,
):
    """expand 双读：仅旧 newapi:channel:cfg:{id} 仍命中"""
    fake_redis.hashes[OLD_KEY] = {
        "limit_quota": "700", "window_hours": "8", "cooldown_seconds": "1200",
    }
    _wire(monkeypatch, fake_redis, models=[_MODEL_3])
    resp = platform_admin_client.get(CHANNELS_URL)
    assert resp.status_code == 200, resp.text
    row = resp.json()["data"][0]
    assert row["gateway_ref"] == "3"
    assert row["effective_source"] == "channel"
    assert row["config"]["limit_quota"] == 700


def test_channels_anonymous_401(client, monkeypatch, fake_redis):
    _wire(monkeypatch, fake_redis)
    assert client.get(CHANNELS_URL).status_code == 401


def _assert_hidden_404(resp) -> None:
    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert body["code"] == "HTTP_404"
    assert body.get("data") in ({}, None)
    text = resp.text.lower()
    assert "sk-" not in text
    assert "需要平台管理员" not in (body.get("message") or "")
    assert "抱歉" not in (body.get("message") or "")


@pytest.mark.parametrize("role_client", ["viewer_client", "operator_client", "admin_client"])
def test_channels_non_platform_admin_404(role_client, request, monkeypatch, fake_redis):
    _wire(monkeypatch, fake_redis, models=[_MODEL_3])
    resp = request.getfixturevalue(role_client).get(CHANNELS_URL)
    _assert_hidden_404(resp)
    assert "m3" not in resp.text


def test_channels_remote_unreachable_200_empty(
    platform_admin_client, monkeypatch, fake_redis,
):
    """远端不可达 → 200 空列表（不 502；71.3 由 overview 信封承担）"""
    _wire(monkeypatch, fake_redis, list_error=RuntimeError("conn refused"))
    resp = platform_admin_client.get(CHANNELS_URL)
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == "SUCCESS"
    assert resp.json()["data"] == []


def test_set_config_admin_writes_relay_hash_and_audits(
    platform_admin_client, monkeypatch, fake_redis,
):
    _wire(monkeypatch, fake_redis, models=[_MODEL_3])
    audit_mock = AsyncMock()
    import backend.app.api.v1.newapi as api_mod
    monkeypatch.setattr(api_mod, "record_audit", audit_mock)

    resp = platform_admin_client.put(f"{CHANNELS_URL}/3/config", json={
        "limit_quota": 800, "window_hours": 6, "cooldown_seconds": 900,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["channel_id"] == 3
    assert data["config"]["limit_quota"] == 800

    fields = fake_redis.hashes[RELAY_KEY_3]
    assert fields["limit_quota"] == "800"
    assert fields["window_hours"] == "6"
    assert fields["cooldown_seconds"] == "900"
    assert OLD_KEY not in fake_redis.hashes

    audit_mock.assert_awaited_once()
    call_args = audit_mock.await_args.args
    assert call_args[2] == "newapi.channel_config.set"
    assert call_args[3] == "channel:3"


def test_set_config_ref_writes_relay_string(
    platform_admin_client, monkeypatch, fake_redis,
):
    _wire(monkeypatch, fake_redis, models=[_MODEL_GPT])
    resp = platform_admin_client.put(f"{MODELS_CFG_URL}/gpt-4o/config", json={
        "limit_quota": 100, "window_hours": 24, "cooldown_seconds": 60,
    })
    assert resp.status_code == 200, resp.text
    assert fake_redis.hashes[RELAY_KEY_GPT]["limit_quota"] == "100"
    assert resp.json()["data"]["gateway_ref"] == "gpt-4o"


def test_set_config_unknown_channel_404(platform_admin_client, monkeypatch, fake_redis):
    _wire(monkeypatch, fake_redis, models=[])
    resp = platform_admin_client.put(f"{CHANNELS_URL}/99/config", json={
        "limit_quota": 100, "window_hours": 24, "cooldown_seconds": 3600,
    })
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"
    assert fake_redis.hashes == {}


@pytest.mark.parametrize("payload", [
    {"limit_quota": 10, "window_hours": 0, "cooldown_seconds": 60},
    {"limit_quota": 10, "window_hours": 721, "cooldown_seconds": 60},
    {"limit_quota": 10, "window_hours": 24, "cooldown_seconds": 59},
    {"limit_quota": -1, "window_hours": 24, "cooldown_seconds": 60},
])
def test_set_config_validation_422(platform_admin_client, monkeypatch, fake_redis, payload):
    _wire(monkeypatch, fake_redis, models=[_MODEL_3])
    resp = platform_admin_client.put(f"{CHANNELS_URL}/3/config", json=payload)
    assert resp.status_code == 422, resp.text
    assert fake_redis.hashes == {}


def test_set_config_anonymous_401(client, monkeypatch, fake_redis):
    _wire(monkeypatch, fake_redis, models=[_MODEL_3])
    resp = client.put(f"{CHANNELS_URL}/3/config", json={
        "limit_quota": 10, "window_hours": 24, "cooldown_seconds": 60})
    assert resp.status_code == 401


def test_set_config_viewer_404(viewer_client, monkeypatch, fake_redis):
    _wire(monkeypatch, fake_redis, models=[_MODEL_3])
    resp = viewer_client.put(f"{CHANNELS_URL}/3/config", json={
        "limit_quota": 10, "window_hours": 24, "cooldown_seconds": 60})
    assert resp.status_code == 404
    assert resp.json()["code"] == "HTTP_404"
    assert fake_redis.hashes == {}


def test_set_config_tenant_admin_404_quota_unchanged(
    db_client, admin_client, monkeypatch, fake_redis, db_session,
):
    """GWT-U12.3 写权：租户公司管理员改窗口 → 404 同形；额度不变；越权记录"""
    import asyncio

    from sqlalchemy import select

    from platform_core.models.operation_log import OperationLog

    _wire(monkeypatch, fake_redis, models=[_MODEL_3])
    resp = admin_client.put(f"{CHANNELS_URL}/3/config", json={
        "limit_quota": 10, "window_hours": 24, "cooldown_seconds": 60})
    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == "HTTP_404"
    assert "抱歉" not in resp.text
    assert fake_redis.hashes == {}

    async def _logs():
        async with db_session() as s:
            return list((await s.execute(
                select(OperationLog).where(OperationLog.action == "authz.denied")
            )).scalars().all())

    logs = asyncio.run(_logs())
    assert logs
    assert "config" in logs[0].target


def test_clear_config_admin_returns_previous_and_deletes(
    platform_admin_client, monkeypatch, fake_redis,
):
    fake_redis.hashes[RELAY_KEY_3] = {
        "limit_quota": "500", "window_hours": "12", "cooldown_seconds": "1800",
    }
    _wire(monkeypatch, fake_redis, models=[_MODEL_3])

    resp = platform_admin_client.delete(f"{CHANNELS_URL}/3/config")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["cleared"] is True
    assert data["config"]["limit_quota"] == 500
    assert RELAY_KEY_3 not in fake_redis.hashes


def test_clear_config_without_previous(platform_admin_client, monkeypatch, fake_redis):
    _wire(monkeypatch, fake_redis, models=[_MODEL_3])
    resp = platform_admin_client.delete(f"{CHANNELS_URL}/3/config")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["cleared"] is True
    assert data["config"] is None


def test_clear_config_anonymous_401(client, monkeypatch, fake_redis):
    _wire(monkeypatch, fake_redis)
    assert client.delete(f"{CHANNELS_URL}/3/config").status_code == 401


def test_clear_config_operator_404(operator_client, monkeypatch, fake_redis):
    _wire(monkeypatch, fake_redis)
    resp = operator_client.delete(f"{CHANNELS_URL}/3/config")
    assert resp.status_code == 404
    assert resp.json()["code"] == "HTTP_404"
