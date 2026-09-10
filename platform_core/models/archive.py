"""数据归档（DB 升级 2026-09 Phase C / DB-10）"""
from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import TenantMixin


class ArchiveRecord(TenantMixin, Base):
    """归档快照（spider_results 等增长表的冷热分离；按需恢复）"""

    __tablename__ = "archive_records"
    __table_args__ = (
        UniqueConstraint("source_table", "source_id", name="uq_archive_records_source"),
        Index("ix_archive_records_tenant_archived", "tenant_id", "archived_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    source_table = Column(String(64), nullable=False, comment="来源表名")
    source_id = Column(Integer, nullable=False, comment="来源行 ID")
    archived_at = Column(DateTime(timezone=True), server_default=func.now(), comment="归档时间")
    archived_by = Column(String(64), nullable=True, comment="操作人")
    snapshot = Column(JSON, nullable=False, comment="完整行数据快照")
    retention_until = Column(DateTime(timezone=True), nullable=True, comment="保留截止（NULL=永久）")
