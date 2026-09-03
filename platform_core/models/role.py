"""角色权限域模型（SaaS 化拓展：角色/权限/菜单可见性 DB 单源）

- Role：角色定义（key 唯一；permissions JSON 为权限码集合——菜单可见性
  (menu:*)与按钮级(btn:*)统一收口；内置三角色 seed 于迁移 022，运营面可改）
- /auth/permissions 按 DB 读（角色管理改动即时生效）
"""
from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from platform_core.models.base import Base


class Role(Base):
    """角色表（permissions = 权限码数组；is_builtin 内置角色禁删可改）"""

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("role_key", name="uq_roles_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    role_key = Column(String(32), nullable=False, comment="角色标识（admin/operator/viewer/自定义）")
    name = Column(String(64), nullable=False, comment="显示名")
    description = Column(String(255), nullable=True, comment="职责说明")
    permissions = Column(JSON, nullable=False, comment="权限码数组（menu:*/btn:*）")
    is_builtin = Column(Boolean, nullable=False, default=False, server_default="0",
                        comment="内置角色（禁删，权限可调）")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
