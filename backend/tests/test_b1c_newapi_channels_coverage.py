"""B1c 零 HTTP 覆盖路由清剿——newapi/channels 配置面（3 条路由）

覆盖路由清单（全部 require_admin）：
- GET    /api/v1/newapi/channels                     渠道列表 + 调度配置合并视图
- PUT    /api/v1/newapi/channels/{channel_id}/config  写渠道级额度配置
- DELETE /api/v1/newapi/channels/{channel_id}/config  清除渠道级配置（回退全局默认）

行为契约级口径（newapi 模块将被 LiteLLM 替换，L5：只锁 HTTP 语义 + 副作用，
不锁实现细节，降低退役成本）：
- HTTP 语义：200 信封 code=SUCCESS / 匿名 401 / 非 admin 403 / 渠道不存在 404 /
  参数界外 422 / 远端不可达 502（code=NEWAPI_UNREACHABLE）
- 副作用：写路径必须落到 Redis hash newapi:channel:cfg:{id}（调度器读取契约），
  且记审计动作 newapi.channel_config.set / .clear
- 服务层合并语义（渠道级 > 全局默认 > 未纳管）已由 test_channel_config_service.py
  覆盖，本文件只锁 HTTP 接线，不重复服务层等价类
"""
from unittest.mock import AsyncMock

import pytest

import backend.services.channel_config_service as cfg_mod
from backend.services.newapi_api import NEWAPI_CHANNEL_CFG_PREFIX
from stubs import FakeRedis, fake_settings

CHANNELS_URL = "/api/v1/newapi/channels"
CFG_KEY = f"{NEWAPI_CHANNEL_CFG_PREFIX}3"  # 渠道 3 的配置 hash 键（调度器读取契约）

# 全局默认额度 0：无渠道级配置的渠道「未纳管」（与服务层测试同一判定口径）
_SETTINGS_DEFAULTS = {
    "NEWAPI.DEFAULT_WINDOW_QUOTA": 0,
    "NEWAPI.DEFAULT_WINDOW_HOURS": 24,
    "NEWAPI.DEFAULT_COOLDOWN_SECONDS": 3600,
}


class _StubClient:
    """NewapiApiClient 桩（同步构造工厂 + 异步方法），可预设返回或异常"""

    def __init__(self, channels=None, get_channel=None, list_error=None):
        self._channels = channels or []
        self._get_channel = get_channel
        self._list_error = list_error

    async def list_channels(self):
        if self._list_error is not None:
            raise self._list_error
        return self._channels

    async def get_channel(self, channel_id):
        return self._get_channel


@pytest.fixture
def fake_redis():
    return FakeRedis()


def _wire(monkeypatch, redis: FakeRedis, stub: _StubClient):
    """接线：服务命名空间内的 Redis 门面与 new-api 客户端均替换为桩"""
    monkeypatch.setattr(cfg_mod, "get_async_redis", lambda: redis)
    monkeypatch.setattr(cfg_mod, "NewapiApiClient", lambda **kw: stub)
    monkeypatch.setattr(cfg_mod, "settings", fake_settings(**_SETTINGS_DEFAULTS))


# ---------------------------------------------------------------------------
# GET /api/v1/newapi/channels
# ---------------------------------------------------------------------------

def test_channels_admin_ok_merged_view(admin_client, monkeypatch, fake_redis):
    """admin 合并视图：渠道级配置的渠道 effective_source=channel 且 config 回显；
    无配置渠道（全局默认 0）未纳管（config=null / effective_source=none）"""
    fake_redis.hashes[CFG_KEY] = {
        "limit_quota": "500", "window_hours": "12", "cooldown_seconds": "1800",
    }
    stub = _StubClient(
        channels=[{"id": 3, "name": "prov-a", "status": 1},
                  {"id": 4, "name": "prov-b", "status": 1}],
    )
    _wire(monkeypatch, fake_redis, stub)

    resp = admin_client.get(CHANNELS_URL)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "SUCCESS"
    assert body["success"] is True
    by_id = {row["id"]: row for row in body["data"]}
    assert set(by_id) == {3, 4}
    assert by_id[3]["effective_source"] == "channel"
    assert by_id[3]["config"]["limit_quota"] == 500
    assert by_id[4]["config"] is None
    assert by_id[4]["effective_source"] == "none"


def test_channels_anonymous_401(client, monkeypatch, fake_redis):
    _wire(monkeypatch, fake_redis, _StubClient())
    assert client.get(CHANNELS_URL).status_code == 401


@pytest.mark.parametrize("role_client", ["viewer_client", "operator_client"])
def test_channels_non_admin_403(role_client, request, monkeypatch, fake_redis):
    """viewer/operator 直调（绕过前端菜单隐藏）→ 403：require_admin 守卫存在"""
    _wire(monkeypatch, fake_redis, _StubClient())
    resp = request.getfixturevalue(role_client).get(CHANNELS_URL)
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_channels_remote_unreachable_502(admin_client, monkeypatch, fake_redis):
    """远端 new-api 不可达 → 502 业务码 NEWAPI_UNREACHABLE（不 500）"""
    _wire(monkeypatch, fake_redis, _StubClient(list_error=RuntimeError("conn refused")))
    resp = admin_client.get(CHANNELS_URL)
    assert resp.status_code == 502, resp.text
    assert resp.json()["code"] == "NEWAPI_UNREACHABLE"


# ---------------------------------------------------------------------------
# PUT /api/v1/newapi/channels/{channel_id}/config
# ---------------------------------------------------------------------------

def test_set_config_admin_writes_hash_and_audits(admin_client, monkeypatch, fake_redis):
    """写配置：200 回执 + Redis hash 字段与调度器读取契约一致 + 审计动作落点"""
    stub = _StubClient(get_channel={"id": 3, "name": "prov-a"})
    _wire(monkeypatch, fake_redis, stub)
    audit_mock = AsyncMock()
    import backend.app.api.v1.newapi as api_mod
    monkeypatch.setattr(api_mod, "record_audit", audit_mock)

    resp = admin_client.put(f"{CHANNELS_URL}/3/config", json={
        "limit_quota": 800, "window_hours": 6, "cooldown_seconds": 900,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["channel_id"] == 3
    assert data["config"]["limit_quota"] == 800

    # 副作用 1：hash 字段与 channel_scheduler_service._channel_cfg 读取契约一一对应
    fields = fake_redis.hashes[CFG_KEY]
    assert fields["limit_quota"] == "800"
    assert fields["window_hours"] == "6"
    assert fields["cooldown_seconds"] == "900"

    # 副作用 2：审计动作与目标格式（record_audit(session, user, action, target, detail)）
    audit_mock.assert_awaited_once()
    call_args = audit_mock.await_args.args
    assert call_args[2] == "newapi.channel_config.set"
    assert call_args[3] == "channel:3"


def test_set_config_unknown_channel_404(admin_client, monkeypatch, fake_redis):
    """渠道不存在 → 404（防把配置写到不存在的 ID 上静默空转），hash 零写入"""
    _wire(monkeypatch, fake_redis, _StubClient(get_channel=None))
    resp = admin_client.put(f"{CHANNELS_URL}/99/config", json={
        "limit_quota": 100, "window_hours": 24, "cooldown_seconds": 3600,
    })
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"
    assert fake_redis.hashes == {}  # 拒绝路径零副作用


@pytest.mark.parametrize("payload", [
    {"limit_quota": 10, "window_hours": 0, "cooldown_seconds": 60},    # 窗口界外（ge=1）
    {"limit_quota": 10, "window_hours": 721, "cooldown_seconds": 60},  # 窗口界外（le=720）
    {"limit_quota": 10, "window_hours": 24, "cooldown_seconds": 59},   # 冷却界外（ge=60）
    {"limit_quota": -1, "window_hours": 24, "cooldown_seconds": 60},   # 额度界外（ge=0）
])
def test_set_config_validation_422(admin_client, monkeypatch, fake_redis, payload):
    """参数界外 → 422，且 hash 零写入（副作用断言）"""
    _wire(monkeypatch, fake_redis, _StubClient(get_channel={"id": 3}))
    resp = admin_client.put(f"{CHANNELS_URL}/3/config", json=payload)
    assert resp.status_code == 422, resp.text
    assert fake_redis.hashes == {}


def test_set_config_anonymous_401(client, monkeypatch, fake_redis):
    _wire(monkeypatch, fake_redis, _StubClient(get_channel={"id": 3}))
    resp = client.put(f"{CHANNELS_URL}/3/config", json={
        "limit_quota": 10, "window_hours": 24, "cooldown_seconds": 60})
    assert resp.status_code == 401


def test_set_config_viewer_403(viewer_client, monkeypatch, fake_redis):
    _wire(monkeypatch, fake_redis, _StubClient(get_channel={"id": 3}))
    resp = viewer_client.put(f"{CHANNELS_URL}/3/config", json={
        "limit_quota": 10, "window_hours": 24, "cooldown_seconds": 60})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/v1/newapi/channels/{channel_id}/config
# ---------------------------------------------------------------------------

def test_clear_config_admin_returns_previous_and_deletes(admin_client, monkeypatch, fake_redis):
    """清除：回执携带清除前配置（cleared=True），hash 键被删除"""
    fake_redis.hashes[CFG_KEY] = {
        "limit_quota": "500", "window_hours": "12", "cooldown_seconds": "1800",
    }
    _wire(monkeypatch, fake_redis, _StubClient())

    resp = admin_client.delete(f"{CHANNELS_URL}/3/config")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["cleared"] is True
    assert data["config"]["limit_quota"] == 500  # 回执 = 清除前配置
    assert CFG_KEY not in fake_redis.hashes      # 副作用：键已删除


def test_clear_config_without_previous(admin_client, monkeypatch, fake_redis):
    """无渠道级配置时清除：仍 200（幂等），回执 config=null"""
    _wire(monkeypatch, fake_redis, _StubClient())
    resp = admin_client.delete(f"{CHANNELS_URL}/3/config")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["cleared"] is True
    assert data["config"] is None


def test_clear_config_anonymous_401(client, monkeypatch, fake_redis):
    _wire(monkeypatch, fake_redis, _StubClient())
    assert client.delete(f"{CHANNELS_URL}/3/config").status_code == 401


def test_clear_config_operator_403(operator_client, monkeypatch, fake_redis):
    _wire(monkeypatch, fake_redis, _StubClient())
    resp = operator_client.delete(f"{CHANNELS_URL}/3/config")
    assert resp.status_code == 403
