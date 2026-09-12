"""出站拉数钥匙（FR-51 / ADR-0020）：只拉本企业结果的租户凭证平面。

与渠道组令牌（relay_tokens，sk-）分平面：本表只存 SHA-256 指纹 + 前缀，
明文只在签发响应出现一次、不落库；禁止与 relay 域混表/混查找集合
（互否执法见出站拉数路径，T-05）。TenantMixin，禁止豁免（PIT-3/4）。
"""
from sqlalchemy import Column, DateTime, Index, Integer, String
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import TenantMixin


class OutboundKey(TenantMixin, Base):
    """一把本企业出站拉数钥匙。

    状态由 revoked_at 派生（NULL=active，非空=revoked 终态），无 status 列、
    无软删（吊销即终态审计，行留）。tenant_id 写路径必填（PIT-4：禁止 NULL=平台）。
    """

    __tablename__ = "outbound_keys"
    __table_args__ = (
        Index("idx_outbound_keys_tenant_created", "tenant_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    name = Column(String(64), nullable=True, comment="备注名；NULL=未起名，列表主展示仍是前缀")
    key_prefix = Column(String(16), nullable=False, comment="再进页可见前缀；应用保证不以 sk- 开头")
    key_hash = Column(String(64), nullable=False, unique=True, comment="SHA-256 指纹；明文不落库")
    issued_by_user_id = Column(Integer, nullable=False, comment="签发者用户 id；无 FK（用户可删，钥匙留审计）")
    revoked_at = Column(DateTime(), nullable=True, comment="吊销时间；NULL=active，非空=revoked（终态，禁止清回 NULL）")
    created_at = Column(DateTime(), server_default=func.now(), nullable=False, comment="签发时刻")
    updated_at = Column(DateTime(), server_default=func.now(), onupdate=func.now(), nullable=False, comment="更新时间")
