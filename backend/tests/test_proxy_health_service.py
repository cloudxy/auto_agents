"""代理池健康管理单测 - ProxyHealthService（盲区补测）

约定：不连真实 Redis/网络，Redis 用 stubs.FakeRedis（内存语义），
httpx 探测用桩客户端，settings 用 stubs.fake_settings patch 模块命名空间。

覆盖（核心公开方法直测）：
- start：开关关闭不开循环、不建连接
- _decay_score：扣分并下限 0.0
- _health_check_once：低分代理探测成功恢复评分 / 探测异常扣分 /
  无低分代理与空评分表跳过
- get_proxy_health：评分+统计合并、字段映射、按分降序
"""
import json
from unittest.mock import MagicMock, patch

import pytest

import backend.services.proxy_health_service as proxy_mod
from backend.services.proxy_health_service import ProxyHealthService
from platform_core.queues import PROXY_SCORES_KEY, PROXY_STATS_KEY
from stubs import FakeRedis, fake_settings


class _HeadClientStub:
    """httpx.AsyncClient 桩：head 返回预设状态码或抛预设异常"""

    def __init__(self, status_code: int = 200, error: Exception | None = None, **kwargs):
        self.status_code = status_code
        self.error = error
        self.kwargs = kwargs
        self.head_calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def head(self, url, **kwargs):
        self.head_calls.append(url)
        if self.error is not None:
            raise self.error
        return MagicMock(status_code=self.status_code)


def _service(redis: FakeRedis | None = None) -> ProxyHealthService:
    svc = ProxyHealthService()
    svc._redis = redis
    return svc


# ---------------- start：开关守卫 ----------------
@pytest.mark.asyncio
async def test_start_disabled_returns_without_loop():
    """PROXY_HEALTH.ENABLED=false：直接返回，不建连接、不启动循环"""
    svc = ProxyHealthService()
    with patch.object(proxy_mod, "settings", fake_settings(**{"PROXY_HEALTH.ENABLED": False})):
        await svc.start()

    assert svc._loop_task is None
    assert svc._redis is None
    assert svc._running is False


# ---------------- _decay_score ----------------
@pytest.mark.asyncio
async def test_decay_score_applies_and_floors_at_zero():
    """扣分生效且下限 0.0：0.8-0.1=0.7；0.05-0.1 → 0.0"""
    redis = FakeRedis()
    redis.hashes[PROXY_SCORES_KEY] = {"http://p1": "0.8", "http://p2": "0.05"}
    svc = _service(redis)

    await svc._decay_score("http://p1", 0.1)
    await svc._decay_score("http://p2", 0.1)

    scores = redis.hashes[PROXY_SCORES_KEY]
    assert scores["http://p1"] == "0.7"
    assert float(scores["http://p2"]) == 0.0  # 不出现负分


# ---------------- _health_check_once ----------------
@pytest.mark.asyncio
async def test_health_check_once_recovers_low_score_proxy():
    """低分代理探测成功（HTTP < 500）：评分恢复到 RECOVER_SCORE 并更新 last_check"""
    redis = FakeRedis()
    redis.hashes[PROXY_SCORES_KEY] = {"http://low1": "0.2"}
    svc = _service(redis)
    stub = _HeadClientStub(status_code=200)
    settings_kv = {
        "PROXY_HEALTH.ENABLED": True,
        "PROXY_HEALTH.LOW_SCORE_THRESHOLD": 0.5,
        "PROXY_HEALTH.RECOVER_SCORE": 0.5,
        "PROXY_HEALTH.PROBE_URL": "http://probe.test/get",
        "PROXY_HEALTH.PROBE_TIMEOUT": 5,
    }
    with patch.object(proxy_mod, "settings", fake_settings(**settings_kv)), \
         patch.object(proxy_mod.httpx, "AsyncClient", lambda **kw: stub):
        await svc._health_check_once()

    assert stub.head_calls == ["http://probe.test/get"]
    assert redis.hashes[PROXY_SCORES_KEY]["http://low1"] == "0.5"  # 恢复评分
    stats = json.loads(redis.hashes[PROXY_STATS_KEY]["http://low1"])
    assert stats["last_check"] != ""  # 探测时间戳被更新


@pytest.mark.asyncio
async def test_health_check_once_decays_on_probe_error():
    """探测异常：评分继续下降（扣 SCORE_DECAY=0.1）"""
    redis = FakeRedis()
    redis.hashes[PROXY_SCORES_KEY] = {"http://low1": "0.4"}
    svc = _service(redis)
    stub = _HeadClientStub(error=RuntimeError("network unreachable"))
    with patch.object(proxy_mod, "settings", fake_settings(**{
            "PROXY_HEALTH.LOW_SCORE_THRESHOLD": 0.5})), \
         patch.object(proxy_mod.httpx, "AsyncClient", lambda **kw: stub):
        await svc._health_check_once()

    assert float(redis.hashes[PROXY_SCORES_KEY]["http://low1"]) == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_health_check_once_skips_when_no_low_scores_or_empty():
    """无低分代理 / 评分表为空：不发起任何探测请求"""
    redis = FakeRedis()
    redis.hashes[PROXY_SCORES_KEY] = {"http://healthy": "0.9"}
    svc = _service(redis)
    stub = _HeadClientStub()
    with patch.object(proxy_mod, "settings", fake_settings(**{
            "PROXY_HEALTH.LOW_SCORE_THRESHOLD": 0.5})), \
         patch.object(proxy_mod.httpx, "AsyncClient", lambda **kw: stub):
        await svc._health_check_once()
        assert stub.head_calls == []  # 高分代理不探测

        redis.hashes[PROXY_SCORES_KEY] = {}
        await svc._health_check_once()
        assert stub.head_calls == []  # 空表直接返回


# ---------------- get_proxy_health ----------------
@pytest.mark.asyncio
async def test_get_proxy_health_merges_scores_and_stats_sorted():
    """评分+统计合并为排行 dict：字段映射 / 坏 JSON 容错 / 按评分降序"""
    redis = FakeRedis()
    redis.hashes[PROXY_SCORES_KEY] = {"http://low": "0.2", "http://high": "0.9"}
    redis.hashes[PROXY_STATS_KEY] = {
        "http://low": json.dumps(
            {"success": 3, "fail": 7, "avg_latency": 1.2345, "last_check": "2026-08-31T10:00:00"}),
        "http://high": "{broken-json",  # 坏 JSON → 统计字段回退默认值
    }
    svc = _service()
    with patch.object(proxy_mod, "settings", fake_settings()), \
         patch.object(proxy_mod.aioredis, "from_url", lambda *a, **kw: redis):
        result = await svc.get_proxy_health()

    assert [row["proxy"] for row in result] == ["http://high", "http://low"]  # 降序
    high = result[0]
    assert high["score"] == 0.9 and high["success"] == 0  # 坏 JSON 统计回退 0
    low = result[1]
    assert low["score"] == 0.2 and low["fail"] == 7
    assert low["avg_latency"] == 1.234  # round 3
    assert low["last_check"] == "2026-08-31T10:00:00"
