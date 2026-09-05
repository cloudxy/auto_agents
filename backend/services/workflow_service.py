"""通用工作流引擎 - 状态机 service 骨架（DB 升级 2026-09 / DB-09）

四表模型（platform_core/models/workflow.py）上的最小状态机：
- start_instance：按 definition.steps_config 展开步骤行，实例 pending → running
- complete_step：步骤 completed → 推进 current_step；末步完成时实例 completed
- cancel_instance：实例 cancelled（未完成步骤置 skipped）

每步状态变更写 workflow_transitions 留痕（trigger_type: auto/manual）。
步骤拓扑当前支持线性串行（steps_config 顺序即执行序）；并行/条件分支为
后续迭代扩展点（step_type 已预留 parallel/condition）。
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.logger import get_logger
from platform_core.models.workflow import (
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowStep,
    WorkflowTransition,
)
from platform_core.repository import BaseRepository

logger = get_logger("api")

# 实例合法状态流转（终态不可再流转）
INSTANCE_TRANSITIONS = {
    "pending": {"running", "cancelled"},
    "running": {"waiting", "completed", "failed", "cancelled"},
    "waiting": {"running", "cancelled", "failed"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}


class WorkflowError(ValueError):
    """工作流状态机非法操作"""


class WorkflowService:
    """工作流定义/实例/步骤状态机（骨架）"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.def_repo = BaseRepository(WorkflowDefinition, session)
        self.inst_repo = BaseRepository(WorkflowInstance, session)

    # ---------- 定义 ----------
    async def create_definition(self, payload: Dict[str, Any]) -> WorkflowDefinition:
        """创建流程定义（steps_config 必须为非空 key/type 列表）"""
        steps = payload.get("steps_config") or []
        if not steps:
            raise WorkflowError("steps_config 不能为空")
        for i, s in enumerate(steps):
            if not s.get("key") or not s.get("type"):
                raise WorkflowError(f"steps_config[{i}] 缺 key/type")
        definition = await self.def_repo.create(
            name=payload["name"],
            description=payload.get("description"),
            steps_config=steps,
            triggers_config=payload.get("triggers_config"),
            created_by=payload.get("created_by"),
        )
        await self.session.commit()
        logger.info(f"创建工作流定义: {definition.name}（{len(steps)} 步）")
        return definition

    # ---------- 实例 ----------
    async def start_instance(self, definition_id: int, context: Optional[Dict] = None,
                             created_by: Optional[str] = None) -> WorkflowInstance:
        """发起实例：展开步骤行 + pending → running + 指向首步"""
        definition = await self.def_repo.get_by_id(definition_id)
        if definition is None:
            raise WorkflowError(f"工作流定义不存在: {definition_id}")
        if definition.status != "active":
            raise WorkflowError(f"定义非 active 不可发起（当前 {definition.status}）")

        instance = await self.inst_repo.create(
            definition_id=definition_id,
            context=context or {},
            created_by=created_by,
        )
        for s in definition.steps_config:
            self.session.add(WorkflowStep(
                instance_id=instance.id, step_key=s["key"], step_type=s["type"],
            ))
        await self._transition_instance(instance, "running")
        first = definition.steps_config[0]["key"]
        instance.current_step = first
        await self.session.commit()
        logger.info(f"工作流实例 #{instance.id} 启动（definition={definition_id} 首步={first}）")
        return instance

    async def complete_step(self, instance_id: int, step_key: str, output: Optional[Dict] = None,
                            operator: Optional[str] = None) -> WorkflowInstance:
        """完成当前步骤并推进（末步完成 → 实例 completed）"""
        instance = await self._get_instance(instance_id)
        if instance.status not in ("running", "waiting"):
            raise WorkflowError(f"实例 #{instance_id} 状态 {instance.status} 不可推进")
        if instance.current_step != step_key:
            raise WorkflowError(
                f"步骤失序：当前 {instance.current_step}，请求完成 {step_key}")

        steps = await self._instance_steps(instance_id)
        step = next(s for s in steps if s.step_key == step_key)
        await self._transition_step(step, "completed", trigger="manual" if operator else "auto",
                                    operator=operator)
        step.output = output

        order = [s.step_key for s in steps]
        idx = order.index(step_key)
        if idx + 1 < len(order):
            instance.current_step = order[idx + 1]
        else:
            instance.current_step = None
            await self._transition_instance(instance, "completed")
        await self.session.commit()
        logger.info(f"工作流实例 #{instance_id} 步骤 {step_key} 完成")
        return instance

    async def cancel_instance(self, instance_id: int, reason: str,
                              operator: Optional[str] = None) -> WorkflowInstance:
        """取消实例：未完成步骤置 skipped，实例 → cancelled"""
        instance = await self._get_instance(instance_id)
        reason_recorded = False
        for s in await self._instance_steps(instance_id):
            if s.status in ("pending", "running"):
                await self._transition_step(s, "skipped", trigger="manual", operator=operator,
                                            reason=None if reason_recorded else reason)
                reason_recorded = True
        await self._transition_instance(instance, "cancelled")
        await self.session.commit()
        logger.info(f"工作流实例 #{instance_id} 取消（{reason}）")
        return instance

    # ---------- 内部 ----------
    async def _get_instance(self, instance_id: int) -> WorkflowInstance:
        instance = await self.inst_repo.get_by_id(instance_id)
        if instance is None:
            raise WorkflowError(f"工作流实例不存在: {instance_id}")
        return instance

    async def _instance_steps(self, instance_id: int) -> List[WorkflowStep]:
        result = await self.session.execute(
            select(WorkflowStep)
            .where(WorkflowStep.instance_id == instance_id)
            .order_by(WorkflowStep.id)
        )
        return list(result.scalars().all())

    async def _transition_instance(self, instance: WorkflowInstance, to_status: str) -> None:
        """实例状态流转（合法性校验 + 起止时刻维护）。

        transitions 表挂 step 级（step_id NOT NULL），实例级流转不写
        transitions——实例生命周期由 status/started_at/completed_at +
        步骤 transitions 链完整还原。
        """
        allowed = INSTANCE_TRANSITIONS.get(instance.status, set())
        if to_status not in allowed:
            raise WorkflowError(f"实例状态 {instance.status} → {to_status} 非法")
        instance.status = to_status
        if to_status == "running" and instance.started_at is None:
            instance.started_at = _now()
        if to_status == "completed":
            instance.completed_at = _now()

    async def _transition_step(self, step: WorkflowStep, to_status: str, *,
                               trigger: str, operator: Optional[str],
                               reason: Optional[str] = None) -> None:
        """步骤状态流转 + transitions 留痕 + 起止时刻维护"""
        from_status = step.status
        step.status = to_status
        if to_status in ("running", "completed") and step.started_at is None:
            step.started_at = _now()
        if to_status in ("completed", "failed", "skipped"):
            step.completed_at = _now()
        self.session.add(WorkflowTransition(
            step_id=step.id, from_status=from_status, to_status=to_status,
            trigger_type=trigger, operator_id=operator, reason=reason,
        ))


def _now() -> datetime:
    """flush 前占位时钟（列级 server_default 语义对齐，UTC aware）"""
    return datetime.now(timezone.utc)
