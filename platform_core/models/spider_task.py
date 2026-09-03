"""爬虫任务模型"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Enum, Index
from sqlalchemy.sql import func
from .base import Base
from .mixins import AuditMixin, SoftDeleteMixin, TenantMixin


class SpiderTask(TenantMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "spider_tasks"
    __table_args__ = (
        Index("ix_spider_tasks_tenant_status", "tenant_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    spider_name = Column(String(100), nullable=False, index=True)
    status = Column(
        Enum("pending", "running", "completed", "failed"),
        default="pending"
    )
    params = Column(Text)  # JSON 字符串
    priority = Column(String(10), default="normal", index=True)  # high/normal/low（阶段 4.1）
    result_count = Column(Integer, default=0)
    retry_count = Column(Integer, default=0)  # 失败自动重试已用次数（上限见 SPIDER_MAX_RETRIES）
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    started_at = Column(DateTime(timezone=True))  # 消费者置 running 的时刻（统计时长用）
    completed_at = Column(DateTime(timezone=True))
