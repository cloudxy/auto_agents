"""DB 升级 2026-09 Phase A（DB-01~03）：Mixin + Repository 软删除感知验证

期望值全部来自独立事实源（矩阵常量、字面量），不做同源重算。
覆盖：软删过滤 / soft_delete+restore 往返 / get_all_with_deleted / exists 过滤 /
无 Mixin 表（审计表）行为不变 / TypeError 守卫 / AuditMixin 列落库。
"""
import datetime

import pytest
from sqlalchemy import select

from platform_core.models import (
    AuditMixin,
    LlmTokenUsage,
    SkillReview,
    SoftDeleteMixin,
    SpiderTask,
    Tenant,
    User,
)
from platform_core.repository import BaseRepository


async def _mk_task(session, spider_name: str, status: str = "pending") -> SpiderTask:
    repo = BaseRepository(SpiderTask, session)
    return await repo.create(spider_name=spider_name, status=status, params="{}")


@pytest.mark.asyncio
async def test_soft_delete_filters_get_by_id_and_get_all(db_session):
    """软删后 get_by_id/get_all/exists 均不可见，get_all_with_deleted 可见"""
    async with db_session() as s:
        alive = await _mk_task(s, "hotsearch")
        dead = await _mk_task(s, "weibo")
        repo = BaseRepository(SpiderTask, s)
        assert len(await repo.get_all()) == 2

        assert await repo.soft_delete(dead.id) is True
        # 幂等：已删行再 soft_delete 不匹配（where deleted_at IS NULL）
        assert await repo.soft_delete(dead.id) is False

        assert await repo.get_by_id(dead.id) is None
        assert await repo.get_by_id(alive.id) is not None
        assert len(await repo.get_all()) == 1
        assert await repo.exists(spider_name="weibo") is False
        assert await repo.exists(spider_name="hotsearch") is True
        # 管理视角仍可见
        assert len(await repo.get_all_with_deleted()) == 2

        # 恢复往返
        assert await repo.restore(dead.id) is True
        assert await repo.restore(dead.id) is False
        assert await repo.get_by_id(dead.id) is not None
        assert len(await repo.get_all()) == 2


@pytest.mark.asyncio
async def test_mixin_columns_present_on_matrix_tables():
    """矩阵事实源：软删 12 表 / 审计 10 表抽检 + 属性行为"""
    assert issubclass(Tenant, SoftDeleteMixin)
    assert issubclass(User, SoftDeleteMixin)
    assert issubclass(SpiderTask, SoftDeleteMixin)
    assert issubclass(SpiderTask, AuditMixin)
    # is_deleted 属性语义
    t = SpiderTask(spider_name="x")
    assert t.is_deleted is False
    t.deleted_at = "2026-09-02 00:00:00"
    assert t.is_deleted is True
    # 豁免矩阵：聚合表/审计表无 Mixin
    assert not hasattr(LlmTokenUsage, "deleted_at")
    assert not hasattr(SkillReview, "created_by")


@pytest.mark.asyncio
async def test_audit_mixin_columns_persist(db_session):
    """AuditMixin 列可写入读回（AI plan 场景已用 created_by）"""
    async with db_session() as s:
        repo = BaseRepository(SpiderTask, s)
        task = await repo.create(spider_name="audit-check", created_by="alice", updated_by="bob")
        row = (await s.execute(select(SpiderTask).where(SpiderTask.id == task.id))).scalar_one()
        assert row.created_by == "alice"
        assert row.updated_by == "bob"


@pytest.mark.asyncio
async def test_repo_without_mixin_unchanged_and_guarded(db_session):
    """无 SoftDeleteMixin 表：get_all 不加过滤；soft_delete 抛 TypeError"""
    async with db_session() as s:
        s.add(LlmTokenUsage(
            tenant_id=None, provider_name="config", model="gpt-4o-mini",
            stat_date=datetime.date(2026, 9, 2), prompt_tokens=1, completion_tokens=2,
            total_tokens=3, request_count=1,
        ))
        await s.commit()
        repo = BaseRepository(LlmTokenUsage, s)
        rows = await repo.get_all()
        assert len(rows) == 1  # 无 deleted_at 列 → 无过滤，行为与升级前一致

        with pytest.raises(TypeError):
            await repo.soft_delete(rows[0].id)
        with pytest.raises(TypeError):
            await repo.restore(rows[0].id)
        # 物理删除仍可用
        assert await repo.delete(rows[0].id) is True
        assert len(await repo.get_all()) == 0
