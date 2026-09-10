"""附件系统（DB 升级 2026-09 Phase B / DB-06）"""
from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import TenantMixin


class Attachment(TenantMixin, Base):
    """附件登记表（file_path 指向 platform_core/storage 实际存储位置）"""

    __tablename__ = "attachments"
    __table_args__ = (
        Index("ix_attachments_resource", "resource_type", "resource_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    resource_type = Column(String(32), nullable=False, comment="资源类型（模型名小写下划线）")
    resource_id = Column(Integer, nullable=False, comment="资源 ID")
    file_name = Column(String(255), nullable=False, comment="原始文件名")
    file_path = Column(String(512), nullable=False, comment="存储路径")
    file_size = Column(BigInteger, nullable=False, default=0, comment="字节数")
    mime_type = Column(String(128), nullable=True, comment="MIME 类型")
    uploaded_by = Column(String(64), nullable=True, comment="上传人")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
