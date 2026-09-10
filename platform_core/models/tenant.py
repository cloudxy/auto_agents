"""租户模型（SaaS S1-1）"""
from sqlalchemy import JSON, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import SoftDeleteMixin


class Tenant(SoftDeleteMixin, Base):
    """租户表：slug 全局唯一；quota 为三类配额 JSON（S3 消费）；status 含到期降级语义"""

    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="租户ID")
    # 普通索引 ix_tenants_slug 已于 026 删除（与 unique 唯一键同列，纯重复）
    slug = Column(String(64), nullable=False, unique=True, comment="租户标识（全局唯一）")
    name = Column(String(128), nullable=False, comment="企业名称")
    status = Column(String(16), nullable=False, default="active", server_default="active",
                    comment="active/expired/disabled")
    quota = Column(JSON, comment="{task_concurrency, result_storage, llm_tokens_month}")
    expires_at = Column(DateTime, comment="套餐到期时间（NULL=不过期）")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    def __repr__(self) -> str:
        return f"<Tenant {self.slug} status={self.status}>"
