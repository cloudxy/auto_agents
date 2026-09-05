"""DB 升级 2026-09 Phase B/C：横切功能表 + 工作流状态机骨架验证（DB-05~12）

期望值来自独立事实源（表清单常量、状态字面量），不做同源重算。
"""
import pytest

from backend.services.workflow_service import WorkflowError, WorkflowService
from platform_core.models import (
    ArchiveRecord,
    Attachment,
    I18nLocale,
    Notification,
    ResourceVersion,
    SystemCache,
    Tag,
    Tagging,
)

PHASE_BC_TABLES = {
    "tags", "taggings", "attachments", "notifications", "resource_versions",
    "workflow_definitions", "workflow_instances", "workflow_steps",
    "workflow_transitions", "archive_records", "i18n_locales",
    "i18n_translations", "system_caches",
}


def test_phase_bc_tables_registered():
    """13 张新表全部注册进 ORM（事实源 = 迁移 020/021 create_table 清单）"""
    from platform_core.models import Base
    assert PHASE_BC_TABLES <= set(Base.metadata.tables.keys())


@pytest.mark.asyncio
async def test_cross_cutting_rows_roundtrip(db_session):
    """标签/附件/通知/版本/归档/缓存 最小行落库读回"""
    async with db_session() as s:
        tag = Tag(tenant_id=None, name="hot", color="#ff5500", created_by="alice")
        s.add(tag)
        await s.flush()
        s.add(Tagging(tag_id=tag.id, resource_type="spider_task", resource_id=1))
        s.add(Attachment(tenant_id=None, resource_type="spider_task", resource_id=1,
                         file_name="a.csv", file_path="storage/a.csv", file_size=10))
        s.add(Notification(tenant_id=1, user_id=1, type="task_completed", title="done"))
        s.add(ResourceVersion(tenant_id=None, resource_type="skill", resource_id=1,
                              version_number=1, snapshot={"name": "x"}))
        s.add(ArchiveRecord(tenant_id=None, source_table="spider_results", source_id=9,
                            snapshot={"url": "http://x"}))
        s.add(SystemCache(cache_key="cfg:v1", cache_value="{}"))
        await s.commit()

        from sqlalchemy import func, select
        for model, expected in [
            (Tag, 1), (Tagging, 1), (Attachment, 1), (Notification, 1),
            (ResourceVersion, 1), (ArchiveRecord, 1), (SystemCache, 1),
        ]:
            n = (await s.execute(select(func.count()).select_from(model))).scalar_one()
            assert n == expected, f"{model.__tablename__} 应为 {expected} 行"


def _steps():
    return [
        {"key": "plan", "type": "action"},
        {"key": "approve", "type": "approval"},
        {"key": "publish", "type": "action"},
    ]


@pytest.mark.asyncio
async def test_workflow_engine_happy_path(db_session):
    """定义→发起→逐步完成→实例 completed；非法流转被状态机拒绝"""
    async with db_session() as s:
        svc = WorkflowService(s)
        definition = await svc.create_definition(
            {"name": "采集上线", "steps_config": _steps(), "created_by": "alice"})
        assert definition.status == "draft"

        # draft 定义不可发起
        with pytest.raises(WorkflowError):
            await svc.start_instance(definition.id)

        definition.status = "active"
        await s.commit()
        inst = await svc.start_instance(definition.id, context={"url": "x"}, created_by="alice")
        assert inst.status == "running"
        assert inst.current_step == "plan"

        # 失序完成被拒
        with pytest.raises(WorkflowError):
            await svc.complete_step(inst.id, "approve")

        await svc.complete_step(inst.id, "plan", output={"ok": True}, operator="bob")
        assert inst.current_step == "approve"
        await svc.complete_step(inst.id, "approve", operator="boss")
        await svc.complete_step(inst.id, "publish")
        assert inst.status == "completed"
        assert inst.current_step is None
        assert inst.completed_at is not None

        # 终态不可再流转
        with pytest.raises(WorkflowError):
            await svc.complete_step(inst.id, "plan")

        # transitions 留痕：3 步 × completed
        from platform_core.models import WorkflowTransition
        from sqlalchemy import func, select
        n = (await s.execute(select(func.count()).select_from(WorkflowTransition))).scalar_one()
        assert n == 3


@pytest.mark.asyncio
async def test_workflow_cancel_skips_pending_steps(db_session):
    """取消实例：未完成步骤置 skipped，原因留痕"""
    async with db_session() as s:
        svc = WorkflowService(s)
        definition = await svc.create_definition({"name": "可取消", "steps_config": _steps()})
        definition.status = "active"
        await s.commit()
        inst = await svc.start_instance(definition.id)
        await svc.complete_step(inst.id, "plan")
        await svc.cancel_instance(inst.id, reason="需求变更", operator="alice")
        assert inst.status == "cancelled"

        from platform_core.models import WorkflowStep
        from sqlalchemy import select as sel
        steps = (await s.execute(
            sel(WorkflowStep).where(WorkflowStep.instance_id == inst.id)
            .order_by(WorkflowStep.id))).scalars().all()
        assert [st.status for st in steps] == ["completed", "skipped", "skipped"]


@pytest.mark.asyncio
async def test_workflow_empty_steps_rejected(db_session):
    """steps_config 空/缺 key 被拒"""
    async with db_session() as s:
        svc = WorkflowService(s)
        with pytest.raises(WorkflowError):
            await svc.create_definition({"name": "空流程", "steps_config": []})
        with pytest.raises(WorkflowError):
            await svc.create_definition({"name": "坏流程", "steps_config": [{"type": "action"}]})


@pytest.mark.asyncio
async def test_i18n_locale_model_roundtrip(db_session):
    """i18n 语言表最小行（种子由迁移 021 负责，此处仅模型行为）"""
    async with db_session() as s:
        s.add(I18nLocale(code="ja", name="日本語", is_default=False, enabled=True))
        await s.commit()
        row = (await s.execute(
            __import__("sqlalchemy").select(I18nLocale).where(I18nLocale.code == "ja")
        )).scalar_one()
        assert row.enabled is True
        assert row.is_default is False
