"""部门域模型（SaaS 化拓展：租户 → 部门 → 成员的组织树一层）

中转站等资源的分配粒度：个人 / 部门 / 公司——部门是公司内分组。
"""
from sqlalchemy import Column, Computed, DateTime, Integer, SmallInteger, String, UniqueConstraint
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import SoftDeleteMixin


class Department(SoftDeleteMixin, Base):
    """部门表（租户内唯一名；软删除；成员经 users.department_id 挂接）

    唯一键含生成列 alive_flag（迁移 025）：存活行参与唯一（同名互斥），软删行
    NULL 脱离唯一约束——删后可重建同名部门（组织重组高频路径）。
    """

    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", "alive_flag", name="uq_departments_tenant_name_alive"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    tenant_id = Column(Integer, nullable=False, index=True, comment="所属租户")
    name = Column(String(64), nullable=False, comment="部门名")
    description = Column(String(255), nullable=True, comment="职责说明")
    alive_flag = Column(SmallInteger, Computed("CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END"),
                        comment="存活标记（生成列，025）：唯一键组件，软删行 NULL 脱离唯一约束")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
