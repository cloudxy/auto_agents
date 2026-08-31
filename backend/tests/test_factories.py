"""E0.1b 模型工厂验证（工单 02）：builder 可 flush、可覆盖、默认值跨调用唯一

Seam（工单预确认）：factories.build_* 公共函数（db_session fixture 上直接验证）。
期望值均为字面量（独立事实源），不回读实现计算。
"""
import pytest
from sqlalchemy import func, select

from platform_core.models.llm_provider import LlmProvider
from platform_core.models.spider_definition import SpiderDefinition
from platform_core.models.spider_task import SpiderTask
from platform_core.models.user import User

from factories import (
    build_llm_provider,
    build_spider_definition,
    build_spider_task,
    build_user,
)


@pytest.mark.asyncio
async def test_builders_flush_under_sqlite(db_session):
    """四个 builder 的产物全部满足列约束，可直接 add_all + flush"""
    async with db_session() as s:
        s.add_all(
            [
                build_user(),
                build_spider_task(),
                build_llm_provider(),
                build_spider_definition(),
            ]
        )
        await s.flush()
        assert (
            await s.execute(select(func.count()).select_from(User))
        ).scalar_one() == 1
        assert (
            await s.execute(select(func.count()).select_from(SpiderTask))
        ).scalar_one() == 1
        assert (
            await s.execute(select(func.count()).select_from(LlmProvider))
        ).scalar_one() == 1
        assert (
            await s.execute(select(func.count()).select_from(SpiderDefinition))
        ).scalar_one() == 1


@pytest.mark.asyncio
async def test_builder_overrides_customize_fields(db_session):
    """关键字段可覆盖定制（名字/状态/优先级/协议）"""
    user = build_user(username="custom-user")
    task = build_spider_task(spider_name="custom_spider", status="running", priority="high")
    provider = build_llm_provider(name="custom-provider", model="gpt-4o-mini", is_active=True)
    definition = build_spider_definition(name="custom_def", type="api", enabled=False)

    assert user.username == "custom-user"
    assert task.spider_name == "custom_spider" and task.status == "running" and task.priority == "high"
    assert provider.name == "custom-provider" and provider.model == "gpt-4o-mini" and provider.is_active is True
    assert definition.name == "custom_def" and definition.type == "api" and definition.enabled is False

    async with db_session() as s:
        s.add_all([user, task, provider, definition])
        await s.commit()


@pytest.mark.asyncio
async def test_builder_defaults_unique_across_calls(db_session):
    """连续默认调用产出唯一键不冲突——llm_providers.name 有 unique 约束，撞库即 IntegrityError"""
    async with db_session() as s:
        s.add_all([build_llm_provider(), build_llm_provider(), build_llm_provider()])
        await s.commit()
        assert (
            await s.execute(select(func.count()).select_from(LlmProvider))
        ).scalar_one() == 3
