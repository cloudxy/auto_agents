"""菜单域模型（SaaS 化：菜单结构 DB 化，运营面可管）

menus 自引用树（parent_id）；permission 关联权限码（NULL=登录可见）；
前端登录后经 /auth/menus 拉取按权限过滤的动态菜单树（DB miss 回退前端静态配置）。
"""
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from platform_core.models.base import Base


class Menu(Base):
    """菜单项（树形：顶级 parent_id=NULL；路由菜单 path 必填，分组可空）"""

    __tablename__ = "menus"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    parent_id = Column(Integer, nullable=True, index=True, comment="父菜单（NULL=顶级）")
    name = Column(String(64), nullable=False, comment="菜单名")
    path = Column(String(128), nullable=True, comment="路由（分组为空）")
    icon = Column(String(64), nullable=True, comment="图标标识（前端映射）")
    permission = Column(String(64), nullable=True, comment="所需权限码（NULL=登录可见）")
    sort_order = Column(Integer, nullable=False, default=100, server_default="100",
                        comment="同级排序（升序）")
    visible = Column(Boolean, nullable=False, default=True, server_default="1",
                     comment="是否启用（下线不展示）")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
