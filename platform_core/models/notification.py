"""通知系统（DB 升级 2026-09 Phase B / DB-07）"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import TenantMixin


class Notification(TenantMixin, Base):
    """站内通知（task_completed/alert/system 等类型；接收人维度已读管理）"""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_inbox", "tenant_id", "user_id", "is_read", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="接收人")
    type = Column(String(32), nullable=False, comment="通知类型（task_completed/alert/system）")
    title = Column(String(255), nullable=False, comment="标题")
    content = Column(Text, nullable=True, comment="详情")
    resource_type = Column(String(32), nullable=True, comment="关联资源类型")
    resource_id = Column(Integer, nullable=True, comment="关联资源 ID")
    is_read = Column(Boolean, nullable=False, default=False, comment="已读标记")
    read_at = Column(DateTime(timezone=True), nullable=True, comment="已读时间")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
