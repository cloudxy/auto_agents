"""爬虫定义模型 - 注册表元数据迁库（3.3）

DB 承接 config/default/spiders.yml 的 SPIDERS 元数据（yml 保留为种子）；
代码级爬虫文件仍在 scrapy/spiders/，DB 只管元数据，不破坏 B2 边界。
"""
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import AuditMixin, SoftDeleteMixin, TenantMixin


class SpiderDefinition(TenantMixin, SoftDeleteMixin, AuditMixin, Base):
    """爬虫定义表（注册表元数据，可调度爬虫清单的 DB 数据源）"""

    __tablename__ = "spider_definitions"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    name = Column(String(50), nullable=False, index=True,
                  comment="爬虫名（租户内唯一）")
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_spider_definitions_tenant_name"),
    )
    title = Column(String(100), nullable=False, comment="展示标题")
    type = Column(String(20), nullable=False, default="web",
                  comment="类型：api/web/custom/flow（驱动前端参数表单）")
    description = Column(Text, nullable=True, comment="描述")
    source = Column(String(20), nullable=False, default="yml_seed", server_default="yml_seed",
                    comment="来源：yml_seed（种子迁移）/ manual（手动登记）/ ai_generated（AI 生成）")
    enabled = Column(Boolean, nullable=False, default=True, server_default="1",
                     comment="是否启用（停用后注册表不再下发）")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(),
                        comment="更新时间")

    def __repr__(self) -> str:
        return f"<SpiderDefinition {self.name}({self.type})>"
