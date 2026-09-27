"""收款通道运行凭据（FR-U31 / ADR-0024）：一行 = 一个通道的一套密文。

平台级：禁止 TenantMixin、禁止 tenant_id 列。同 PR 登记 TENANT_EXEMPT_TABLES。
明文密钥永不落库 / git / yml / 浏览器 / 日志 / Redis。从未配置 = 零行。
"""
from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from platform_core.models.base import Base


class PaymentChannelCredential(Base):
    """一个收款通道的一套运行凭据（密文 blob）。"""

    __tablename__ = "payment_channel_credentials"
    __table_args__ = (
        UniqueConstraint("channel", name="uk_payment_channel_credentials_channel"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="代理主键")
    channel = Column(String(16), nullable=False, comment="alipay/wechat；一通道一行")
    merchant_no = Column(String(64), nullable=False, comment="商户号，可掩码；不是密钥")
    secrets_encrypted = Column(
        Text, nullable=False,
        comment="不透明密文 blob。明文永不落库/git/yml/浏览器/日志/Redis",
    )
    key_version = Column(
        Integer, nullable=False, default=1, server_default="1",
        comment="每轮换 +1；旧密文不保留",
    )
    rotated_at = Column(DateTime, nullable=True, comment="NULL=从未轮换")
    created_by = Column(String(64), nullable=True, comment="超管用户名")
    updated_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
