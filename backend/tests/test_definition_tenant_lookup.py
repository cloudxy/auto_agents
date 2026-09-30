"""爬虫定义按名查找的租户隔离（审计 BUG-17 回归）

名字只在租户内唯一。调度 / 入队走平台态（无租户作用域）时，原先按名取定义会取到别的
租户的行——连同它的 params（目标 URL、选择器）一起塞进本租户任务；删除时的引用检查
也会被别的租户的同名任务挡住。
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from backend.repositories.spider_definition_repository import SpiderDefinitionRepository
from backend.services.spider_task_service import SpiderTaskService
from platform_core.models.spider_definition import SpiderDefinition
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant


def _seed(db_session) -> tuple[int, int]:
    async def _go():
        async with db_session() as s:
            a, b = Tenant(slug="def-a", name="甲"), Tenant(slug="def-b", name="乙")
            s.add_all([a, b])
            await s.flush()
            s.add_all([
                SpiderDefinition(tenant_id=a.id, name="shop", title="甲的店铺", enabled=True,
                                 params={"urls": ["https://secret-a.example/list"]}),
                SpiderDefinition(tenant_id=b.id, name="shop", title="乙的店铺", enabled=True,
                                 params={"urls": ["https://b.example/list"]}),
            ])
            await s.commit()
            return int(a.id), int(b.id)
    return asyncio.run(_go())


def test_platform_context_lookup_uses_owner_tenant_params(db_session):
    a, b = _seed(db_session)

    async def _go():
        async with db_session() as s:  # 平台态：无租户作用域（调度器 / 消费者路径）
            svc = SpiderTaskService(s)
            return (await svc._definition_default_params("shop", b),
                    await svc._definition_default_params("shop", a))

    params_b, params_a = asyncio.run(_go())
    assert "b.example" in params_b and "secret-a" not in params_b
    assert "secret-a" in params_a


def test_get_by_name_explicit_tenant_and_no_multiple_rows_error(db_session):
    a, b = _seed(db_session)

    async def _go():
        async with db_session() as s:
            repo = SpiderDefinitionRepository(s)
            return (await repo.get_by_name("shop", b), await repo.get_by_name("shop"))

    row_b, any_row = asyncio.run(_go())
    assert row_b.tenant_id == b
    assert any_row is not None  # 原先 scalar_one_or_none → MultipleResultsFound 被吞，跳过校验


def test_delete_not_blocked_by_other_tenant_task(db_session):
    a, b = _seed(db_session)

    async def _go():
        async with db_session() as s:
            s.add(SpiderTask(spider_name="shop", tenant_id=a, status="running", params="{}"))
            await s.commit()
        async with db_session() as s:
            deleted_b = await SpiderDefinitionRepository(s).delete_if_unreferenced("shop", b)
            deleted_a = await SpiderDefinitionRepository(s).delete_if_unreferenced("shop", a)
            await s.commit()
        async with db_session() as s:
            left = (await s.execute(select(SpiderDefinition.tenant_id))).scalars().all()
        return deleted_b, deleted_a, left

    deleted_b, deleted_a, left = asyncio.run(_go())
    assert deleted_b is True   # 乙没有任务引用 → 可删（原先被甲的同名任务挡住）
    assert deleted_a is False  # 甲自己的任务仍在引用 → 不删
    assert left == [a]


def test_platform_level_definition_visible_to_tenants_but_own_first(db_session):
    """平台级定义（tenant_id 为空）对所有租户可见；本租户同名定义优先"""
    a, b = _seed(db_session)

    async def _go():
        async with db_session() as s:
            s.add(SpiderDefinition(tenant_id=None, name="builtin", title="平台内置", enabled=True))
            s.add(SpiderDefinition(tenant_id=None, name="shop", title="平台同名", enabled=True))
            await s.commit()
        async with db_session() as s:
            repo = SpiderDefinitionRepository(s)
            return (await repo.get_by_name("builtin", b), await repo.get_by_name("shop", b))

    builtin, shop = asyncio.run(_go())
    assert builtin is not None and builtin.tenant_id is None
    assert shop.tenant_id == b  # 本租户的同名定义优先于平台级
