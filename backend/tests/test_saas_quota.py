"""S3-1 配额契约与检查点验证（工单 39）

Seam（工单预确认）：QuotaService 三检查点 + 超限业务码（db_session 直测）。
"""
from datetime import date

import pytest

from backend.services.quota_service import (
    DEFAULT_QUOTA, QuotaExceededException, QuotaService, quota_of,
)
from platform_core.models.llm_token_usage import LlmTokenUsage
from platform_core.models.spider_result import SpiderResult
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant


_SEQ = 0


async def _tenant(db_session, **quota) -> int:
    global _SEQ
    _SEQ += 1
    async with db_session() as s:
        t = Tenant(slug=f"q-{_SEQ}", name="Q", quota=quota or None)
        s.add(t)
        await s.commit()
        async with db_session() as s2:
            return (await s2.execute(
                __import__("sqlalchemy").select(Tenant).where(Tenant.slug == f"q-{_SEQ}")
            )).scalar_one().id


@pytest.mark.asyncio
async def test_default_quota_merge(db_session):
    """行级 quota 与平台默认逐键合并（部分覆盖生效）"""
    async with db_session() as s:
        t = Tenant(slug="q-merge", name="Q", quota={"task_concurrency": 99})
        s.add(t)
        await s.flush()
        merged = quota_of(t)
    assert merged["task_concurrency"] == 99
    assert merged["result_storage"] == DEFAULT_QUOTA["result_storage"]


@pytest.mark.asyncio
async def test_task_concurrency_over_limit_rejected(db_session):
    tid = await _tenant(db_session, task_concurrency=2)
    async with db_session() as s:
        s.add_all([
            SpiderTask(spider_name="t1", tenant_id=tid, status="running", params="{}"),
            SpiderTask(spider_name="t2", tenant_id=tid, status="pending", params="{}"),
        ])
        await s.commit()
    async with db_session() as s:
        with pytest.raises(QuotaExceededException, match="任务并发"):
            await QuotaService(s).check_task_concurrency(tid)


@pytest.mark.asyncio
async def test_result_storage_over_limit_rejected(db_session):
    tid = await _tenant(db_session, result_storage=1)
    async with db_session() as s:
        s.add(SpiderResult(task_id=1, spider_name="x", url="https://u", tenant_id=tid))
        await s.commit()
    async with db_session() as s:
        with pytest.raises(QuotaExceededException, match="结果存储"):
            await QuotaService(s).check_result_storage(tid)


@pytest.mark.asyncio
async def test_llm_tokens_month_over_limit_rejected(db_session):
    tid = await _tenant(db_session, llm_tokens_month=100)
    async with db_session() as s:
        s.add(LlmTokenUsage(
            tenant_id=tid, provider_name="provider:1", model="m",
            stat_date=date(2026, 9, 1), total_tokens=150,
        ))
        await s.commit()
    async with db_session() as s:
        with pytest.raises(QuotaExceededException, match="LLM token"):
            await QuotaService(s).check_llm_tokens_month(tid, "2026-09")


@pytest.mark.asyncio
async def test_usage_overview_shape(db_session):
    tid = await _tenant(db_session)
    async with db_session() as s:
        s.add_all([
            SpiderTask(spider_name="a", tenant_id=tid, status="running", params="{}"),
            LlmTokenUsage(tenant_id=tid, provider_name="provider:1", model="m",
                          stat_date=date(2026, 9, 1), total_tokens=50),
            LlmTokenUsage(tenant_id=tid, provider_name="provider:2", model="m",
                          stat_date=date(2026, 9, 2), total_tokens=30),
        ])
        await s.commit()
    async with db_session() as s:
        overview = await QuotaService(s).usage_overview(tid, "2026-09")
    assert overview["usage"]["task_concurrency"] == 1
    assert overview["usage"]["llm_tokens_month"] == 80
    assert overview["llm_by_provider"] == {"provider:1": 50, "provider:2": 30}
    assert overview["quota"]["task_concurrency"] == DEFAULT_QUOTA["task_concurrency"]


def test_quota_exception_is_429():

    exc = QuotaExceededException("x")
    assert exc.status_code == 429
