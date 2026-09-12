"""用户模型"""
from sqlalchemy import (
    Boolean, Column, Computed, DateTime, Integer, SmallInteger, String,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from platform_core.models.base import Base
from platform_core.models.mixins import SoftDeleteMixin, TenantMixin


class User(TenantMixin, SoftDeleteMixin, Base):
    """用户表（S1 租户化：tenant_id/tenant_role/is_platform_admin；唯一 (tenant_id, username)）

    T5 租户隔离：继承 TenantMixin——tenant_scope 下 SELECT 自动注入 tenant_id
    过滤（with_loader_criteria）、before_flush 断言新行归属；跨租户查询单点
    收口于 UserRepository.get_by_username（登录消歧，R13 口径声明见该处）。

    子类覆盖 Mixin 的 tenant_id 列仅为收紧 nullable=False（迁移 024：NULL 租户
    语义消灭，(tenant_id, username) 唯一键真正生效）；Mixin 本身保持可空——
    llm_providers 平台公共行的 NULL 是读共享设计而非债务。平台超管挂 platform
    租户（slug='platform'），不再以 NULL 表达。

    唯一键在册化（迁移 042 / T-24 FR-93）：两键均带尾列 alive_flag 生成列
    （capability_assets L58 同款）——存活行 alive_flag=1 参与判重；已删行
    NULL 脱离唯一（MySQL 唯一索引不对含 NULL 行判重）→ 软删行释放
    username（同租户口径）/email（全局口径），恢复正确性由约束兜底。
    """
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "username", "alive_flag",
                         name="uq_users_tenant_username_alive"),
        UniqueConstraint("email", "alive_flag", name="uq_users_email_alive"),
    )

    id = Column(Integer, primary_key=True, comment="用户ID")
    username = Column(String(50), nullable=False, index=True, comment="用户名")
    email = Column(String(100), nullable=False, comment="邮箱")
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    is_active = Column(Boolean, default=True, comment="是否激活")
    is_admin = Column(Boolean, default=False, comment="是否管理员（存量标记，等价 admin 角色）")
    # tenant_id 单列索引已于 026 删除（被 uq_users_tenant_username 最左前缀承接）
    tenant_id = Column(Integer, nullable=False,
                       comment="所属租户（平台超管挂 platform 租户）")
    tenant_role = Column(String(20), comment="租户角色：owner/admin/operator/viewer")
    department_id = Column(Integer, comment="所属部门（departments.id；SaaS 组织树一层）")
    is_platform_admin = Column(Boolean, nullable=False, default=False, server_default="0",
                               comment="平台超级管理员（跨租户，挂 platform 租户）")
    role = Column(String(20), nullable=False, default="operator", server_default="operator",
                  comment="角色：admin(全权)/operator(操作)/viewer(只读)")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    alive_flag = Column(SmallInteger,
                        Computed("CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END"),
                        comment="存活标记（生成列，042）：唯一键组件，软删行 NULL 脱离唯一约束")

    def __repr__(self):
        return f"<User {self.username}>"
