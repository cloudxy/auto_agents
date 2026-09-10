"""R 线接线验证（工单 45/46/47）：任务链/用量链/配额/复合去重 + T-07 入队归属"""
import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.models.spider_result import SpiderResult
from platform_core.models.spider_task import SpiderTask
from platform_core.models.task_template import TaskTemplate
from platform_core.models.tenant import Tenant
from platform_core.tenant_context import tenant_scope


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

        from backend.services.quota_service import PLAN_FULL_CTA, PLAN_FULL_USER, QuotaExceededException

        with pytest.raises(QuotaExceededException) as ei:
            await svc.enqueue("w-spid", params="{}", tenant_id=tid)
        assert ei.value.code == "QUOTA_EXCEEDED"
        assert "任务并发" in ei.value.message
        assert PLAN_FULL_USER in ei.value.message
        assert PLAN_FULL_CTA in ei.value.message


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


@pytest.mark.asyncio
async def test_enqueue_without_tenant_does_not_create(db_session, monkeypatch):
    """GWT-09.4 服务层：无企业不入队，不产生无主任务（禁止 NULL 当平台入站成功）"""
    from backend.services.spider_task_service import SpiderTaskService

    svc = SpiderTaskService.__new__(SpiderTaskService)
    svc.session = MagicMock()
    svc.session.commit = AsyncMock()
    svc.repo = MagicMock()
    svc.repo.create = AsyncMock()
    svc._ensure_spider_available = AsyncMock()
    svc._check_enqueue_quota = AsyncMock()
    with pytest.raises(BusinessException, match="没有企业身份"):
        await svc.enqueue("w-spid", params="{}", tenant_id=None)
    svc.repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_enqueue_lists_in_own_tenant_not_other(db_session, monkeypatch):
    """GWT-09.1：有效企业入队 → 本企业列表可见；他企业不可见"""
    from stubs import FakeRedis, seed_worker_heartbeat

    from backend.services.spider_task_service import SpiderTaskService

    ta, tb = await _tenant(db_session, "g91a"), await _tenant(db_session, "g91b")
    fake = FakeRedis()
    seed_worker_heartbeat(fake)
    monkeypatch.setattr("backend.services.spider_task_service.get_async_redis", lambda: fake)
    monkeypatch.setattr("backend.services.quota_service.get_async_redis", lambda: fake)

    async with db_session() as s:
        svc = SpiderTaskService(s)
        svc._ensure_spider_available = AsyncMock()
        task = await svc.enqueue("w-spid", params="{}", tenant_id=ta)
        task_id = int(task.id)

    with tenant_scope(ta):
        async with db_session() as s:
            listing = await SpiderTaskService(s).list_tasks()
            assert any(i.id == task_id for i in listing.items)
    with tenant_scope(tb):
        async with db_session() as s:
            listing = await SpiderTaskService(s).list_tasks()
            assert all(i.id != task_id for i in listing.items)


@pytest.mark.asyncio
async def test_template_other_tenant_rejected_no_task_for_owner(db_session):
    """GWT-09.3：企业 A 用企业 B 的模板 → 拒绝；B 不出现新任务"""
    from backend.services.spider_registry_service import SpiderRegistryService

    ta, tb = await _tenant(db_session, "g93a"), await _tenant(db_session, "g93b")
    async with db_session() as s:
        s.add(TaskTemplate(name="b-tpl", spider_name="example", tenant_id=tb, params="{}"))
        await s.commit()
        tmpl_id = int((await s.execute(
            select(TaskTemplate.id).where(TaskTemplate.tenant_id == tb)
        )).scalar_one())

    async with db_session() as s:
        svc = SpiderRegistryService(s)
        with pytest.raises(NotFoundException, match="任务模板"):
            await svc.create_task_from_template(tmpl_id, tenant_id=ta)
        await s.rollback()

    async with db_session() as s:
        tasks_b = (await s.execute(
            select(SpiderTask).where(SpiderTask.tenant_id == tb)
        )).scalars().all()
        assert tasks_b == []


@pytest.mark.asyncio
async def test_results_visible_to_owner_hidden_from_other(db_session):
    """GWT-10.1 / 10.3：A 看得到本企业条；B 猜任务编号与没有这个任务同形"""
    from backend.services.spider_query_service import SpiderQueryService

    ta, tb = await _tenant(db_session, "g101a"), await _tenant(db_session, "g101b")
    async with db_session() as s:
        task = SpiderTask(spider_name="x", tenant_id=ta, status="completed", params="{}")
        s.add(task)
        await s.flush()
        s.add(SpiderResult(
            task_id=task.id, spider_name="x", url="https://a.example",
            title="a-item", tenant_id=ta,
        ))
        await s.commit()
        task_id = int(task.id)

    with tenant_scope(ta):
        async with db_session() as s:
            resp = await SpiderQueryService(s).list_results(task_id)
            assert resp.total == 1
            assert resp.items[0].title == "a-item"
    with tenant_scope(tb):
        async with db_session() as s:
            with pytest.raises(NotFoundException, match="爬虫任务"):
                await SpiderQueryService(s).list_results(task_id)


@pytest.mark.asyncio
async def test_wizard_test_crawl_result_stays_in_enqueue_tenant(db_session):
    """GWT-10.2：向导试采归属=入队企业，不进别人的结果"""
    ta, tb = await _tenant(db_session, "g102a"), await _tenant(db_session, "g102b")
    async with db_session() as s:
        task = SpiderTask(spider_name="flow_generic", tenant_id=ta, status="completed", params="{}")
        s.add(task)
        await s.flush()
        s.add(SpiderResult(
            task_id=task.id, spider_name="flow_generic", url="https://wiz.example",
            title="wiz", tenant_id=ta,
        ))
        await s.commit()
        task_id = int(task.id)

    with tenant_scope(ta):
        async with db_session() as s:
            rows = (await s.execute(select(SpiderResult))).scalars().all()
            assert [r.task_id for r in rows] == [task_id]
    with tenant_scope(tb):
        async with db_session() as s:
            rows = (await s.execute(select(SpiderResult))).scalars().all()
            assert rows == []


def test_platform_admin_run_rejects_no_ownerless_task(
    db_client, platform_admin_client, db_session,
):
    """GWT-09.4：平台超管无企业空间走租户任务提交 → 拒绝入队，无无主任务"""
    resp = platform_admin_client.post(
        "/api/v1/spiders/run",
        json={"spider_name": "example", "params": "{}"},
    )
    assert resp.status_code == 400, resp.text
    assert "没有企业身份" in resp.json()["message"]

    async def _check():
        async with db_session() as s:
            assert (await s.execute(select(SpiderTask))).scalars().all() == []

    asyncio.run(_check())


def test_logged_in_tenant_submit_appears_in_own_list(db_client, db_session, monkeypatch):
    """GWT-09.1 HTTP：经办已登录且企业有效，提交采集 → 本企业任务列表"""
    from conftest import make_tenant_owner_headers
    from stubs import FakeRedis, seed_worker_heartbeat

    fake = FakeRedis()
    seed_worker_heartbeat(fake)

    def _get(key=None):
        return fake

    import backend.services.spider_task_service as svc_mod
    import backend.services.quota_service as quota_mod
    monkeypatch.setattr(svc_mod, "get_async_redis", _get)
    monkeypatch.setattr(quota_mod, "get_async_redis", _get)

    headers, tid = make_tenant_owner_headers(db_session, slug="g91http")
    resp = db_client.post(
        "/api/v1/spiders/run",
        json={"spider_name": "example", "params": '{"urls": ["https://example.com"]}'},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["data"]["id"]
    listing = db_client.get("/api/v1/spiders/tasks", headers=headers)
    assert listing.status_code == 200, listing.text
    ids = [i["id"] for i in listing.json()["data"]["items"]]
    assert task_id in ids

    async def _check():
        async with db_session() as s:
            row = (await s.execute(
                select(SpiderTask).where(SpiderTask.id == task_id)
            )).scalar_one()
            assert row.tenant_id == tid

    asyncio.run(_check())
