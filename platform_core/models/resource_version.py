"""版本系统（DB 升级 2026-09 Phase B / DB-08）"""
from sqlalchemy import JSON, Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import TenantMixin


class ResourceVersion(TenantMixin, Base):
    """资源版本快照（version_number 由 service 层在事务内自增分配）"""

    __tablename__ = "resource_versions"
    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", "version_number",
                         name="uq_resource_versions_rid"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    resource_type = Column(String(32), nullable=False, comment="资源类型（模型名小写下划线）")
    resource_id = Column(Integer, nullable=False, index=True, comment="资源 ID")
    version_number = Column(Integer, nullable=False, comment="版本号（自增）")
    snapshot = Column(JSON, nullable=False, comment="完整字段快照")
    change_summary = Column(String(512), nullable=True, comment="变更摘要")
    changed_by = Column(String(64), nullable=True, comment="操作人")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
