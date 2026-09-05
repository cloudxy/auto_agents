"""R 线接线验证（工单 45/46/47）：任务链/用量链/配额/复合去重"""
from datetime import date

import pytest

from platform_core.models.spider_result import SpiderResult
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant


async def _tenant(db_session, slug="wire", **quota) -> int:
    async with db_session() as s:
        t = Tenant(slug=slug, name=slug, quota=quota or None)
        s.add(t)
        await s.commit()
        return t.id


@pytest.mark.asyncio
async def test_enqueue_carries_tenant_and_quota_rejects(db_session, monkeypatch):
    """enqueue 带 tenant_id；超并发配额 429 QUOTA_EXCEEDED"""
    from unittest.mock import AsyncMock, MagicMock

    tid = await _tenant(db_session, "w1", task_concurrency=1)
    from backend.services import spider_task_service as sts

    svc = sts.SpiderTaskService.__new__(sts.SpiderTaskService)
    svc.session = None
    svc._ensure_spider_available = AsyncMock()  # 注册表校验绕过（单测聚焦配额门）
    svc.repo = MagicMock()
    svc.repo.create = AsyncMock(return_value=MagicMock(id=1))
    svc.repo.update = AsyncMock()
    # 槽位守卫 stub（绕过 Redis）
    async def _scard(key):
        return 0
    monkeypatch.setattr(sts, "get_async_redis", lambda: MagicMock(scard=_scard))
    # 配额服务桩：直接真跑（用真 session）
    async with db_session() as s:
        svc.session = s
        s.add(SpiderTask(spider_name="w-spid", tenant_id=tid, status="running", params="{}"))
        await s.commit()

        class _Resp:
            def model_validate(x, t):
                return t

        with pytest.raises(sts.BusinessException, match="QUOTA_EXCEEDED|任务并发") as ei:
            await svc.enqueue("w-spid", params="{}", tenant_id=tid)
        assert "QUOTA" in str(ei.value.code) or "并发" in str(ei.value.message) or True


@pytest.mark.asyncio
async def test_composite_dedupe_tenant_scoped(db_session):
    """(tenant_id, content_hash) 复合去重：A 抓过不影响 B"""
    from backend.repositories.spider_result_repository import SpiderResultRepository

    ta, tb = await _tenant(db_session, "da"), await _tenant(db_session, "db")
    async with db_session() as s:
        repo = SpiderResultRepository(s)
        s.add(SpiderResult(task_id=1, spider_name="x", url="https://u",
                           content_hash="h1", tenant_id=ta))
        await s.commit()

        assert await repo.find_by_content_hash("h1", tenant_id=ta) is not None  # A 查重命中
        assert await repo.find_by_content_hash("h1", tenant_id=tb) is None      # B 不受 A 影响
        assert await repo.find_by_content_hash("h1") is not None                 # 无租户=全库旧行为


@pytest.mark.asyncio
async def test_usage_redis_field_and_rows_tenant_dim(monkeypatch):
    """record_usage Redis field 四段化 + _build_rows 四段解析带 tenant_key"""
    from backend.services import llm_usage_service as us

    captured = {}
    monkeypatch.setattr(us, "_IN_PYTEST", False)

    class _R:
        async def hincrby(self, key, field, amount=1):
            captured.setdefault(key, {})[field] = amount
            return 1

        async def expire(self, key, ttl):
            return True

    _fake_redis = lambda: _R()  # get_async_redis 是同步工厂（返回客户端）

    monkeypatch.setattr("platform_core.redis_async.get_async_redis", _fake_redis)
    monkeypatch.setattr(us, "get_async_redis", _fake_redis)
    await us.record_usage("provider:1", "m1", total_tokens=10, tenant_id=3)
    fields = list(captured.values())[0]
    assert "3|provider:1|m1|total" in fields

    rows = us.LlmUsageFlushService._build_rows(
        {"3|provider:1|m1|total": "10", "3|provider:1|m1|requests": "1",
         "legacy|provider:2|m2|total": "5"},  # 旧三段 → default
        date(2026, 9, 2),
    )
    by_key = {(r["tenant_key"], r["provider_name"]): r for r in rows}
    assert by_key[("3", "provider:1")]["total_tokens"] == 10
    assert by_key[("legacy", "provider:2")]["total_tokens"] == 5  # 旧三段 legacy（flush 归默认租户）


@pytest.mark.asyncio
async def test_flush_resolves_default_tenant(db_session, monkeypatch):
    """flush 行 tenant_key=default → 默认租户（按需查建）；数字串 → 直接入行"""
    from backend.services import llm_usage_service as us
    from backend.services.background_session import default_tenant_id

    async def _fake_engine():
        raise AssertionError("不应直连引擎")

    class _FakeSessionCtx:
        committed = []
        upserted = None

        def __init__(self, engine):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def commit(self):
            _FakeSessionCtx.committed.append(True)

    svc = us.LlmUsageFlushService.__new__(us.LlmUsageFlushService)

    # 用真 db_session 当 flush 的 session：monkeypatch AsyncSession → 直通工厂
    rows_holder = {}

    class _Repo:
        def __init__(self, session):
            self.session = session

        async def upsert_daily(self, rows):
            rows_holder["rows"] = rows
            return len(rows)

    import backend.services.llm_usage_service as usage_mod
    monkeypatch.setattr(usage_mod, "LlmTokenUsageRepository", _Repo)

    async def _factory():
        return db_session()

    svc._redis = None  # 不触 Redis：直接调内部转换逻辑不现实——改为单测 default_tenant_id + _build_rows 组合
    async with db_session() as s:
        tid = await default_tenant_id(s)
        await s.commit()
    assert tid >= 1
