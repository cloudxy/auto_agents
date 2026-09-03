"""标签系统（DB 升级 2026-09 Phase B / DB-05）

多态关联统一约定：resource_type + resource_id（取值 = 模型名小写下划线，
如 spider_task / skill / capability_asset / llm_provider / workflow_definition）。
"""
from sqlalchemy import Column, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import TenantMixin


class Tag(TenantMixin, Base):
    """标签主表（tenant_id NULL = 全局标签；租户内唯一）"""

    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tags_tenant_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    name = Column(String(64), nullable=False, comment="标签名")
    color = Column(String(7), nullable=True, comment="十六进制色值（前端渲染）")
    created_by = Column(String(64), nullable=True, comment="创建人")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")


class Tagging(Base):
    """多态关联表（资源 ↔ 标签）；随资源生命周期由 service 层清理"""

    __tablename__ = "taggings"
    __table_args__ = (
        Index("uq_taggings_resource_tag", "resource_type", "resource_id", "tag_id", unique=True),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    tag_id = Column(Integer, nullable=False, index=True, comment="标签 ID")
    resource_type = Column(String(32), nullable=False, comment="资源类型（模型名小写下划线）")
    resource_id = Column(Integer, nullable=False, comment="资源 ID")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
