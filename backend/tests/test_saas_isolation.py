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


# ---------------- T8：豁免清单外移（注册机制） ----------------

def test_exempt_registry_wired_from_single_source():
    """T8：唯一事实源（backend/app/tenant_isolation.py）经组装点 create_app 注册生效

    conftest 的 autouse app fixture 已跑 create_app（豁免登记随组装点完成），
    此处断言注册路径真实落地——组装断线时豁免/共享读语义静默失效，靠此测试拦截。
    另覆盖注册机制本身：可增量登记 + 幂等（platform_core 只提供机制，零业务表名）。
    """
    from backend.app.tenant_isolation import (
        PLATFORM_SHARED_READ_TABLES,
        TENANT_EXEMPT_TABLES,
    )
    from platform_core import tenant_context
    from platform_core.tenant_context import (
        platform_shared_read_tables,
        register_tenant_exempt_tables,
        tenant_exempt_tables,
    )

    assert set(TENANT_EXEMPT_TABLES) <= tenant_exempt_tables()
    assert set(PLATFORM_SHARED_READ_TABLES) <= platform_shared_read_tables()

    # 机制自测：增量登记 + 幂等（探针表名不存在于任何 metadata，登记后即清理）
    register_tenant_exempt_tables("__t8_probe__")
    register_tenant_exempt_tables("__t8_probe__")  # 重复登记幂等
    try:
        assert "__t8_probe__" in tenant_exempt_tables()
        assert set(tenant_exempt_tables()) >= set(TENANT_EXEMPT_TABLES) | {"__t8_probe__"}
    finally:
        tenant_context._TENANT_EXEMPT.discard("__t8_probe__")  # noqa: SLF001 探针清理


@pytest.mark.asyncio
async def test_registered_exempt_update_unfiltered_vs_unregistered_filtered(db_session):
    """T8 行为对拍：注册豁免表（skills，带 tenant_id 列）Core UPDATE 不注入过滤；
    未注册的带 tenant_id 表（spider_tasks）同上下文内仍被注入（rowcount 收窄本租户）"""
    from platform_core.tenant_context import tenant_exempt_tables

    assert "skills" in tenant_exempt_tables()  # 注册路径生效（组装点登记）

    async with db_session() as s:
        s.add_all([
            Skill(name="sk-1", file_path="skills/1"),
            Skill(name="sk-2", file_path="skills/2"),  # 平台级：tenant_id 恒 NULL
            SpiderTask(spider_name="a-task", tenant_id=1, params="{}"),
            SpiderTask(spider_name="b-task", tenant_id=2, params="{}"),
        ])
        await s.commit()

    with tenant_scope(1):
        async with db_session() as s:
            r_exempt = await s.execute(
                update(Skill).values(sync_state="hash_changed")
                .execution_options(synchronize_session=False)
            )
            r_filtered = await s.execute(
                update(SpiderTask).values(status="running")
                .execution_options(synchronize_session=False)
            )
            await s.commit()
            assert r_exempt.rowcount == 2  # 豁免：全表生效（NULL 行不被注入条件失配）
            assert r_filtered.rowcount == 1  # 未豁免：仅本租户行

    async with db_session() as s:
        states = set((await s.execute(select(Skill.sync_state))).scalars().all())
        statuses = {n: st for n, st in (await s.execute(
            select(SpiderTask.spider_name, SpiderTask.status))).all()}
    assert states == {"hash_changed"}
    assert statuses == {"a-task": "running", "b-task": "pending"}
