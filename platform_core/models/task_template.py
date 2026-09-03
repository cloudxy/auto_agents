"""任务模板模型 —— 用户常用任务配置的收藏与复用"""
from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from .base import Base
from .mixins import AuditMixin, SoftDeleteMixin, TenantMixin


class TaskTemplate(TenantMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "spider_task_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_task_templates_tenant_name"),
    )
    spider_name = Column(String(100), nullable=False)
    params = Column(Text)  # JSON 字符串
    priority = Column(String(10), default="normal")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
