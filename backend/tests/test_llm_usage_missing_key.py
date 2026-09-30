"""月度用量键缺失（审计 BUG-29 回归）：键不存在返回 None（不可知），不再读成 0 放行"""
import asyncio

import backend.services.llm_usage_service as mod


class _FakeRedis:
    def __init__(self, data: dict | None):
        self.data = data

    async def exists(self, key):
        return 1 if self.data is not None else 0

    async def hget(self, key, field):
        return (self.data or {}).get(field)

    async def hgetall(self, key):
        return dict(self.data or {})


def _patch(monkeypatch, data):
    monkeypatch.setattr(mod, "_IN_PYTEST", False)
    monkeypatch.setattr(mod, "get_async_redis", lambda *a, **k: _FakeRedis(data))


def test_missing_monthly_key_is_unknown(monkeypatch):
    _patch(monkeypatch, None)
    assert asyncio.run(mod.get_month_used("config", tenant_id=5)) is None
    assert asyncio.run(mod.get_tenant_month_used(5)) is None


def test_existing_key_without_field_is_zero(monkeypatch):
    _patch(monkeypatch, {"9|config|total": "100"})
    assert asyncio.run(mod.get_month_used("other", tenant_id=5)) == 0


def test_existing_key_sums_tenant_fields(monkeypatch):
    _patch(monkeypatch, {"5|a|total": "10", "5|b|total": "20", "6|a|total": "99"})
    assert asyncio.run(mod.get_tenant_month_used(5)) == 30
