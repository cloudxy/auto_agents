"""LLM 供应商多模型子表（方案 B · B-M2-1）

一供应商挂多模型：勾选式增删 + 默认模型 + tier + priority（候选链排序）+ 健康态。
父表 llm_providers.model 保留为"默认模型的冗余快照"——子表 is_default 变更时
由 Service 同事务刷新（消费路径第一阶段零改动）。
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from platform_core.models.base import Base


class LlmProviderModel(Base):
    """供应商模型子表"""

    __tablename__ = "llm_provider_models"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_id", name="uq_provider_model"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    provider_id = Column(
        Integer,
        ForeignKey("llm_providers.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="所属供应商",
    )
    model_id = Column(String(128), nullable=False, comment="平台模型标识")
    alias = Column(String(128), default="", comment="显示别名")
    model_tier = Column(String(16), nullable=False, default="basic",
                        server_default="basic", comment="strong/basic（防故障转移静默降质）")
    priority = Column(Integer, nullable=False, default=100, server_default="100",
                      comment="候选链排序（升序优先）")
    is_default = Column(Boolean, nullable=False, default=False, server_default="0",
                        comment="默认模型（至多一行）")
    enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    health_status = Column(String(16), nullable=False, default="unknown", server_default="unknown",
                           comment="unknown/healthy/degraded/down")
    last_checked_at = Column(DateTime, comment="最近巡检时间")
    last_latency_ms = Column(Integer, comment="最近一次测试延迟")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<LlmProviderModel {self.model_id} default={self.is_default}>"


from platform_core.models.llm_provider import LlmProvider  # noqa: E402（置文件尾避免循环导入）

LlmProvider.models = relationship(
    "LlmProviderModel",
    cascade="all, delete-orphan",
    passive_deletes=True,
    backref="provider",
)
