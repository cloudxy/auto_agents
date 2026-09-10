"""产品事实追加表（Wave 0 FR-15 / ADR-0016）

一行 = 一次已发生的产品事实。tenant_id 是事件主语（可 NULL），不是隔离归属。
禁止 TenantMixin；T-12 同 PR 登记 TENANT_EXEMPT_TABLES。v1 无精确一次键。
"""
from sqlalchemy import JSON, Column, DateTime, Index, Integer, String
from sqlalchemy.sql import func

from platform_core.models.base import Base


class ProductEvent(Base):
    """产品事件（追加；应用永不 UPDATE）"""

    __tablename__ = "product_events"
    __table_args__ = (
        Index("idx_product_events_name_occurred", "event_name", "occurred_at"),
        Index("idx_product_events_tenant_occurred", "tenant_id", "occurred_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="代理主键，跟仓 INT")
    occurred_at = Column(DateTime, nullable=False, comment="业务时间 UTC；切日 Asia/Shanghai")
    event_name = Column(String(64), nullable=False, comment="蓝图字面量；dba 不改口径")
    tenant_id = Column(Integer, nullable=True, comment="NULL=匿名或无法消歧。事件主语，非隔离归属")
    actor_user_id = Column(Integer, nullable=True, comment="匿名 NULL；不加 FK")
    anonymous_id = Column(String(64), nullable=True, comment="浏览匿名身份；signup 必须带回")
    role = Column(String(32), nullable=True, comment="已登录才有")
    props = Column(JSON, nullable=True, comment="非查询列：cta/page/spider/source/result_count/...")
    created_at = Column(
        DateTime, nullable=False, server_default=func.current_timestamp(), comment="记录时间",
    )
    updated_at = Column(
        DateTime, nullable=False, server_default=func.current_timestamp(),
        comment="R-AUD；应用永不更新",
    )

    def __repr__(self) -> str:
        return f"<ProductEvent #{self.id} {self.event_name}>"
