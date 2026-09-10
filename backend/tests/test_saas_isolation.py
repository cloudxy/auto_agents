"""S1-2 行级隔离基座验证（工单 32）：写侧断言 + 读侧注入 + 豁免 + 平台态

Seam（工单预确认）：tenant_context 的作用域助手与事件钩子（db_session 直测）。
"""
import pytest
from sqlalchemy import delete, select, update

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


@pytest.mark.asyncio
async def test_capability_assets_exempt_update_unfiltered(db_session):
    """T-04 / PIT-3：capability_assets 已登记豁免 → 租户态 Core UPDATE 不注入；
    恒 NULL 行全部命中（不豁免则 rowcount=0，超管刷新看不见自己的改动）"""
    from platform_core.models.capability import CapabilityAsset
    from platform_core.tenant_context import tenant_exempt_tables

    assert "capability_assets" in tenant_exempt_tables()
    assert "capability_installs" not in tenant_exempt_tables()

    async with db_session() as s:
        s.add_all([
            CapabilityAsset(asset_type="plugin", name="ca-1", category="plugin"),
            CapabilityAsset(asset_type="plugin", name="ca-2", category="plugin"),
        ])
        await s.commit()

    with tenant_scope(1):
        async with db_session() as s:
            result = await s.execute(
                update(CapabilityAsset).values(sync_state="hash_changed")
                .execution_options(synchronize_session=False)
            )
            await s.commit()
            assert result.rowcount == 2  # 豁免：NULL 行不被注入条件失配

    async with db_session() as s:
        states = set((await s.execute(select(CapabilityAsset.sync_state))).scalars().all())
    assert states == {"hash_changed"}


@pytest.mark.asyncio
async def test_t21_catalog_tables_exempt_and_installs_not(db_session):
    """T-21 / PIT-3：本票平台目录表在豁免清单；capability_installs 不在"""
    from backend.app.tenant_isolation import TENANT_EXEMPT_TABLES
    from platform_core.models.capability import (
        CapabilityAsset, CapabilityCommand, CapabilityComponent,
    )
    from platform_core.tenant_context import tenant_exempt_tables

    for table in ("capability_commands", "capability_components"):
        assert table in TENANT_EXEMPT_TABLES
        assert table in tenant_exempt_tables()
    assert "capability_installs" not in TENANT_EXEMPT_TABLES
    assert "capability_installs" not in tenant_exempt_tables()

    async with db_session() as s:
        parent = CapabilityAsset(asset_type="plugin", name="t21-parent", category="plugin")
        child = CapabilityAsset(asset_type="command", name="t21-child", category="command")
        s.add_all([parent, child])
        await s.flush()
        s.add(CapabilityCommand(asset_id=parent.id, slash="t21", description="d"))
        s.add(CapabilityComponent(
            parent_asset_id=parent.id, child_asset_id=child.id, role="bundled_command",
        ))
        await s.commit()

    with tenant_scope(1):
        async with db_session() as s:
            r_cmd = await s.execute(
                update(CapabilityCommand).values(description="patched")
                .execution_options(synchronize_session=False)
            )
            r_edge = await s.execute(
                update(CapabilityComponent).values(role="uses_skill")
                .execution_options(synchronize_session=False)
            )
            await s.commit()
            assert r_cmd.rowcount == 1  # 已登记豁免：不注入
            assert r_edge.rowcount == 1


@pytest.mark.asyncio
async def test_t29_sources_table_exempt(db_session):
    """T-29 / PIT-3：capability_sources 平台表进豁免清单；租户态 UPDATE 不注入失配。"""
    from backend.app.tenant_isolation import TENANT_EXEMPT_TABLES
    from platform_core.models.capability import CapabilitySource
    from platform_core.tenant_context import tenant_exempt_tables

    assert "capability_sources" in TENANT_EXEMPT_TABLES
    assert "capability_sources" in tenant_exempt_tables()
    assert "capability_installs" not in TENANT_EXEMPT_TABLES

    async with db_session() as s:
        s.add(CapabilitySource(
            name="t29-src", source_kind="local", uri="/tmp/t29", last_succeeded=0,
        ))
        await s.commit()

    with tenant_scope(1):
        async with db_session() as s:
            result = await s.execute(
                update(CapabilitySource).values(last_error="probe")
                .execution_options(synchronize_session=False)
            )
            await s.commit()
            assert result.rowcount == 1


@pytest.mark.asyncio
async def test_t33_aliases_table_exempt(db_session):
    """T-33 / PIT-3：capability_aliases 平台表进豁免清单；安装表仍不在。"""
    from backend.app.tenant_isolation import TENANT_EXEMPT_TABLES
    from platform_core.models.capability import CapabilityAlias, CapabilityAsset
    from platform_core.tenant_context import tenant_exempt_tables

    assert "capability_aliases" in TENANT_EXEMPT_TABLES
    assert "capability_aliases" in tenant_exempt_tables()
    assert "capability_installs" not in TENANT_EXEMPT_TABLES
    assert "capability_installs" not in tenant_exempt_tables()

    async with db_session() as s:
        asset = CapabilityAsset(
            asset_type="skill", name="t33-alias-asset", category="cat-a",
        )
        s.add(asset)
        await s.flush()
        s.add(CapabilityAlias(
            slug="t33-vanity", asset_id=asset.id, asset_type="skill",
        ))
        await s.commit()

    with tenant_scope(1):
        async with db_session() as s:
            result = await s.execute(
                update(CapabilityAlias).values(slug="t33-patched")
                .execution_options(synchronize_session=False)
            )
            await s.commit()
            assert result.rowcount == 1


@pytest.mark.asyncio
async def test_capability_installs_update_delete_injects_tenant_id(db_session):
    """T-25 / PIT-3：capability_installs 禁止豁免 → 租户态 Core UPDATE/DELETE 注入 tenant_id。

    与 test_registered_exempt_update_unfiltered_vs_unregistered_filtered 同形、方向相反：
    豁免表 rowcount=全表；本表 rowcount 收窄本租户。
    """
    from backend.app.tenant_isolation import TENANT_EXEMPT_TABLES
    from platform_core.models.capability import CapabilityAsset, CapabilityInstall
    from platform_core.models.tenant import Tenant
    from platform_core.tenant_context import tenant_exempt_tables

    assert "capability_installs" not in TENANT_EXEMPT_TABLES
    assert "capability_installs" not in tenant_exempt_tables()

    async with db_session() as s:
        s.add_all([
            Tenant(slug="inst-a", name="A"),
            Tenant(slug="inst-b", name="B"),
        ])
        await s.flush()
        ta = (await s.execute(select(Tenant).where(Tenant.slug == "inst-a"))).scalar_one()
        tb = (await s.execute(select(Tenant).where(Tenant.slug == "inst-b"))).scalar_one()
        asset = CapabilityAsset(asset_type="skill", name="inst-skill", category="cat-a")
        s.add(asset)
        await s.flush()
        s.add_all([
            CapabilityInstall(tenant_id=ta.id, asset_id=asset.id, host="grok"),
            CapabilityInstall(tenant_id=tb.id, asset_id=asset.id, host="grok"),
        ])
        await s.commit()
        tid_a, tid_b, aid = int(ta.id), int(tb.id), int(asset.id)

    with tenant_scope(tid_a):
        async with db_session() as s:
            r_upd = await s.execute(
                update(CapabilityInstall).values(enabled=0)
                .execution_options(synchronize_session=False)
            )
            await s.commit()
            assert r_upd.rowcount == 1  # 未豁免：只动本租户

    async with db_session() as s:
        flags = {
            int(tid): int(en)
            for tid, en in (await s.execute(
                select(CapabilityInstall.tenant_id, CapabilityInstall.enabled)
            )).all()
        }
    assert flags[tid_a] == 0
    assert flags[tid_b] == 1

    with tenant_scope(tid_a):
        async with db_session() as s:
            r_del = await s.execute(
                delete(CapabilityInstall).execution_options(synchronize_session=False)
            )
            await s.commit()
            assert r_del.rowcount == 1

    async with db_session() as s:
        left = (await s.execute(select(CapabilityInstall.tenant_id))).scalars().all()
    assert list(left) == [tid_b]
    assert aid  # 资产行仍在（RESTRICT，未级联）
