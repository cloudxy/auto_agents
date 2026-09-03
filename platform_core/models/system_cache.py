"""系统缓存（DB 升级 2026-09 Phase C / DB-12）

TTL 语义：expires_at NULL = 永不过期；service 层数据变更时 DELETE 对应 cache_key 主动失效。
"""
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from platform_core.models.base import Base


class SystemCache(Base):
    """DB 级配置/高频读缓存"""

    __tablename__ = "system_caches"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    cache_key = Column(String(255), nullable=False, unique=True, comment="缓存键")
    cache_value = Column(Text, nullable=False, comment="缓存值")
    expires_at = Column(DateTime(timezone=True), nullable=True, comment="过期时间（NULL=永不过期）")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), comment="更新时间")
