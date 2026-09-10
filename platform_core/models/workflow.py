"""通用工作流引擎（DB 升级 2026-09 Phase B / DB-09，全量版 4 表）

- WorkflowDefinition：steps_config JSON 支持任意拓扑（串行/并行/条件分支/审批）
- WorkflowInstance：一次流程执行（context = 输入参数 + 中间变量）
- WorkflowStep：步骤执行记录（input/output JSON）
- WorkflowTransition：状态流转日志（auto/manual/timeout 全留痕）

状态机驱动见 backend/services/workflow_service.py（骨架）。
"""
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import TenantMixin


class WorkflowDefinition(TenantMixin, Base):
    """流程定义（draft/active/archived）"""

    __tablename__ = "workflow_definitions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_workflow_definitions_tenant_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    name = Column(String(128), nullable=False, comment="流程名")
    description = Column(Text, nullable=True, comment="描述")
    status = Column(String(16), nullable=False, default="draft", server_default="draft",
                    comment="draft/active/archived")
    steps_config = Column(JSON, nullable=False, comment='步骤定义（[{key,type,assignee,conditions}]）')
    triggers_config = Column(JSON, nullable=True, comment="触发条件（事件/定时/手动）")
    created_by = Column(String(64), nullable=True, comment="创建人")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), comment="更新时间")


class WorkflowInstance(TenantMixin, Base):
    """流程实例（pending/running/waiting/completed/failed/cancelled）"""

    __tablename__ = "workflow_instances"
    __table_args__ = (
        Index("ix_workflow_instances_tenant_status", "tenant_id", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    definition_id = Column(Integer, ForeignKey("workflow_definitions.id"), nullable=False,
                           comment="流程定义")
    status = Column(String(16), nullable=False, default="pending", server_default="pending",
                    comment="pending/running/waiting/completed/failed/cancelled")
    context = Column(JSON, nullable=True, comment="运行时上下文（输入参数+中间变量）")
    current_step = Column(String(64), nullable=True, comment="当前步骤 key")
    started_at = Column(DateTime(timezone=True), nullable=True, comment="开始时间")
    completed_at = Column(DateTime(timezone=True), nullable=True, comment="完成时间")
    created_by = Column(String(64), nullable=True, comment="发起人")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), comment="更新时间")


class WorkflowStep(Base):
    """步骤执行记录（pending/running/completed/failed/skipped）"""

    __tablename__ = "workflow_steps"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    instance_id = Column(Integer, ForeignKey("workflow_instances.id"), nullable=False,
                         index=True, comment="所属实例")
    step_key = Column(String(64), nullable=False, comment="步骤标识（对应 steps_config.key）")
    step_type = Column(String(16), nullable=False, comment="action/approval/condition/parallel")
    status = Column(String(16), nullable=False, default="pending", server_default="pending",
                    comment="pending/running/completed/failed/skipped")
    input = Column(JSON, nullable=True, comment="步骤输入")
    output = Column(JSON, nullable=True, comment="步骤输出")
    started_at = Column(DateTime(timezone=True), nullable=True, comment="开始时间")
    completed_at = Column(DateTime(timezone=True), nullable=True, comment="完成时间")


class WorkflowTransition(Base):
    """状态流转日志（auto/manual/timeout 全留痕，审计链）"""

    __tablename__ = "workflow_transitions"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    step_id = Column(Integer, ForeignKey("workflow_steps.id"), nullable=False, index=True,
                     comment="所属步骤")
    from_status = Column(String(16), nullable=True, comment="来源状态")
    to_status = Column(String(16), nullable=False, comment="目标状态")
    trigger_type = Column(String(16), nullable=False, comment="auto/manual/timeout")
    operator_id = Column(String(64), nullable=True, comment="操作人")
    reason = Column(Text, nullable=True, comment="原因说明")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
