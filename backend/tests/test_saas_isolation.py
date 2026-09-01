"""S1-2 行级隔离基座验证（工单 32）：写侧断言 + 读侧注入 + 豁免 + 平台态

Seam（工单预确认）：tenant_context 的作用域助手与事件钩子（db_session 直测）。
"""
import pytest
from sqlalchemy import select, update

from platform_core.models.ai_plan import AiPlan
from platform_core.models.llm_provider import LlmProvider
from platform_core.models.skill import Skill
from platform_core.models.spider_task import SpiderTask
from platform_core.tenant_context import platform_scope, tenant_scope


async def _seed_two_tenants(db_session) -> tuple[int, int]:
    async with db_session() as s:
        s.add_all([
            SpiderTask(spider_name="a-task", tenant_id=1, params="{}"),
            SpiderTask(spider_name="b-task", tenant_id=2, params="{}"),
        ])
        await s.commit()
    return 1, 2


@pytest.mark.asyncio
async def test_write_assertion_rejects_cross_tenant_insert(db_session):
    """租户上下文写入他租户归属行 → 断言拒绝（10.2-A 主防线）"""
    with tenant_scope(1):
        async with db_session() as s:
            s.add(SpiderTask(spider_name="evil", tenant_id=2, params="{}"))
            with pytest.raises(Exception, match="租户"):
                await s.flush()


@pytest.mark.asyncio
async def test_read_injection_hides_other_tenants(db_session):
    await _seed_two_tenants(db_session)
    with tenant_scope(1):
        async with db_session() as s:
            names = (await s.execute(select(SpiderTask.spider_name))).scalars().all()
    assert names == ["a-task"]


@pytest.mark.asyncio
async def test_update_delete_injected_to_own_tenant(db_session):
    """Core update 在租户上下文内被注入条件（state.py 专项同路径）"""
    await _seed_two_tenants(db_session)
    with tenant_scope(1):
        async with db_session() as s:
            result = await s.execute(
                update(SpiderTask).values(status="running").execution_options(synchronize_session=False)
            )
            await s.commit()
            assert result.rowcount == 1  # 只动了 A 的行

    async with db_session() as s:
        statuses = {n: st for n, st in (await s.execute(
            select(SpiderTask.spider_name, SpiderTask.status))).all()}
    assert statuses == {"a-task": "running", "b-task": "pending"}


@pytest.mark.asyncio
async def test_platform_scope_sees_and_writes_all(db_session):
    await _seed_two_tenants(db_session)
    with platform_scope():
        async with db_session() as s:
            names = (await s.execute(select(SpiderTask.spider_name))).scalars().all()
            s.add(SpiderTask(spider_name="p-task", tenant_id=2, params="{}"))
            await s.commit()
    assert set(names) == {"a-task", "b-task"}


@pytest.mark.asyncio
async def test_no_context_keeps_legacy_semantics(db_session):
    """无上下文（存量后台/测试路径）：不注入不过滤——真实请求必经中间件不落此分支"""
    await _seed_two_tenants(db_session)
    async with db_session() as s:
        names = (await s.execute(select(SpiderTask.spider_name))).scalars().all()
    assert set(names) == {"a-task", "b-task"}


@pytest.mark.asyncio
async def test_exempt_tables_not_filtered(db_session):
    """豁免白名单（skills 域等平台级表）不受租户过滤"""
    async with db_session() as s:
        s.add(Skill(name="shared-skill", file_path="skills/shared"))
        await s.commit()
    with tenant_scope(1):
        async with db_session() as s:
            names = (await s.execute(select(Skill.name))).scalars().all()
    assert names == ["shared-skill"]


@pytest.mark.asyncio
async def test_llm_providers_platform_shared_read(db_session):
    """llm_providers 读注入带平台公共行可见性（S4 兜底前提）"""
    async with db_session() as s:
        s.add_all([
            LlmProvider(name="mine", provider_type="openai_compatible",
                        base_url="https://a", model="m", tenant_id=1),
            LlmProvider(name="platform-public", provider_type="openai_compatible",
                        base_url="https://p", model="m", tenant_id=None),
            LlmProvider(name="other-tenant", provider_type="openai_compatible",
                        base_url="https://b", model="m", tenant_id=2),
        ])
        await s.commit()
    with tenant_scope(1):
        async with db_session() as s:
            names = set((await s.execute(select(LlmProvider.name))).scalars().all())
    assert names == {"mine", "platform-public"}  # 本租户 + 平台公共；他租户不可见


@pytest.mark.asyncio
async def test_ai_plan_core_update_injected(db_session):
    """§7.3 专项：ai_planner 的 Core update(AiPlan) 在租户上下文内只影响本租户"""
    async with db_session() as s:
        s.add_all([
            AiPlan(target_url="https://a", status="planning", tenant_id=1),
            AiPlan(target_url="https://b", status="planning", tenant_id=2),
        ])
        await s.commit()
    with tenant_scope(1):
        async with db_session() as s:
            result = await s.execute(
                update(AiPlan).where(AiPlan.status == "planning")
                .values(status="failed").execution_options(synchronize_session=False)
            )
            await s.commit()
            assert result.rowcount == 1
