"""用户模型"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, UniqueConstraint
from sqlalchemy.sql import func
from platform_core.models.base import Base
from platform_core.models.mixins import SoftDeleteMixin


class User(SoftDeleteMixin, Base):
    """用户表（S1 租户化：tenant_id/tenant_role/is_platform_admin；唯一改 (tenant_id, username)）"""
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="uq_users_tenant_username"),
    )

    id = Column(Integer, primary_key=True, comment="用户ID")
    username = Column(String(50), nullable=False, index=True, comment="用户名")
    email = Column(String(100), unique=True, nullable=False, index=True, comment="邮箱")
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    is_active = Column(Boolean, default=True, comment="是否激活")
    is_admin = Column(Boolean, default=False, comment="是否管理员（存量标记，等价 admin 角色）")
    tenant_id = Column(Integer, index=True, comment="所属租户（NULL=平台超管）")
    tenant_role = Column(String(20), comment="租户角色：owner/admin/operator/viewer")
    department_id = Column(Integer, comment="所属部门（departments.id；SaaS 组织树一层）")
    is_platform_admin = Column(Boolean, nullable=False, default=False, server_default="0",
                               comment="平台超级管理员（跨租户，tenant_id 恒 NULL）")
    role = Column(String(20), nullable=False, default="operator", server_default="operator",
                  comment="角色：admin(全权)/operator(操作)/viewer(只读)")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    def __repr__(self):
        return f"<User {self.username}>"
