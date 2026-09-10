"""任务模板模型 —— 用户常用任务配置的收藏与复用"""
from sqlalchemy import Column, Computed, Integer, SmallInteger, String, Text, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from .base import Base
from .mixins import AuditMixin, SoftDeleteMixin, TenantMixin


class TaskTemplate(TenantMixin, SoftDeleteMixin, AuditMixin, Base):
    """任务模板：用户常用任务配置的收藏与复用。

    唯一键含生成列 alive_flag（迁移 025）：软删行脱离唯一约束，删后可重建同名模板。
    """
    __tablename__ = "spider_task_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", "alive_flag", name="uq_task_templates_tenant_name_alive"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    alive_flag = Column(SmallInteger, Computed("CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END"),
                        comment="存活标记（生成列，025）：唯一键组件，软删行 NULL 脱离唯一约束")
    spider_name = Column(String(100), nullable=False)
    params = Column(Text)  # JSON 字符串
    priority = Column(String(10), default="normal")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
