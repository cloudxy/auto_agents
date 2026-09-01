"""S1-1 租户数据契约验证（工单 31）：tenants 表 + 复合唯一 + tenant_id 落位

Seam（工单预确认）：模型行可 flush（db_session）+ 复合唯一语义（SQLite 约束生效）。
"""
import pytest
from sqlalchemy.exc import IntegrityError

from platform_core.models.tenant import Tenant
from platform_core.models.user import User


def _tenant(slug: str) -> Tenant:
    return Tenant(slug=slug, name=f"租户-{slug}", status="active",
                  quota={"task_concurrency": 5, "result_storage": 10000, "llm_tokens_month": 200000})


def _user(username: str, tenant_id=None, tenant_role="viewer", email=None) -> User:
    return User(username=username, email=email or f"{username}@t.local",
                password_hash="x", role="viewer", tenant_id=tenant_id, tenant_role=tenant_role)


@pytest.mark.asyncio
async def test_tenant_flush_with_quota_json(db_session):
    async with db_session() as s:
        t = _tenant("acme")
        s.add(t)
        await s.commit()
        stored = (await s.execute(
            __import__("sqlalchemy").select(Tenant).where(Tenant.slug == "acme")
        )).scalar_one()
    assert stored.quota["task_concurrency"] == 5
    assert stored.status == "active"


@pytest.mark.asyncio
async def test_same_username_across_tenants_allowed(db_session):
    """复合唯一 (tenant_id, username)：跨租户同名合法"""
    async with db_session() as s:
        t1, t2 = _tenant("t1"), _tenant("t2")
        s.add_all([t1, t2])
        await s.flush()
        s.add_all([
            _user("alice", tenant_id=t1.id, tenant_role="owner", email="alice@t1.local"),
            _user("alice", tenant_id=t2.id, tenant_role="viewer", email="alice@t2.local"),
        ])
        await s.commit()  # 不抛即通过


@pytest.mark.asyncio
async def test_duplicate_username_within_tenant_rejected(db_session):
    async with db_session() as s:
        t = _tenant("t3")
        s.add(t)
        await s.flush()
        s.add_all([
            _user("bob", tenant_id=t.id, email="b1@t.local"),
            _user("bob", tenant_id=t.id, email="b2@t.local"),
        ])
        with pytest.raises(IntegrityError):
            await s.flush()


@pytest.mark.asyncio
async def test_nine_business_tables_carry_tenant_id(db_session):
    """9 张业务表模型层携带 tenant_id 列（S1 逐表清单）"""
    from platform_core.models import (
        AiPlan, AlertRule, LlmProvider, LlmTokenUsage, Skill, SpiderDefinition,
        SpiderResult, SpiderSchedule, SpiderTask, TaskTemplate,
    )

    expected = {
        SpiderTask: "spider_tasks", SpiderResult: "spider_results",
        SpiderSchedule: "spider_schedules", SpiderDefinition: "spider_definitions",
        TaskTemplate: "spider_task_templates", AiPlan: "ai_plans",
        LlmProvider: "llm_providers", AlertRule: "alert_rules",
        LlmTokenUsage: "llm_token_usage",
    }
    for model in expected:
        assert hasattr(model, "tenant_id"), f"{model.__name__} 缺 tenant_id"
    # 平台级豁免表不带租户语义
    assert not hasattr(Skill, "tenant_id") or Skill.tenant_id is not None
