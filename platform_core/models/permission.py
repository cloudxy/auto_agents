"""权限资源模型（SaaS 化：权限码注册表，运营面可维护）"""
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from platform_core.models.base import Base


class Permission(Base):
    """权限资源（code 唯一；group 分组陈列；type=menu/btn/api）"""

    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    code = Column(String(64), nullable=False, unique=True, comment="权限码（menu:*/btn:*/api:*）")
    name = Column(String(64), nullable=False, comment="显示名")
    group_name = Column(String(32), nullable=False, default="其他", comment="分组")
    ptype = Column(String(16), nullable=False, default="btn", comment="类型：menu/btn/api")
    description = Column(String(255), nullable=True, comment="说明")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
