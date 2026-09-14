"""租户 API Key —— 外部数据 API 按租户签发，禁止平台静态共享密钥跨租户读。"""
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import AuditMixin, SoftDeleteMixin, TenantMixin


class ApiKey(TenantMixin, SoftDeleteMixin, AuditMixin, Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="密钥备注名")
    key_prefix = Column(String(12), nullable=False, comment="明文前缀（展示用）")
    key_hash = Column(String(64), nullable=False, unique=True, index=True, comment="SHA-256")
    scopes = Column(String(255), nullable=True, comment="逗号分隔 scope，空=结果只读")
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    note = Column(Text, nullable=True)
