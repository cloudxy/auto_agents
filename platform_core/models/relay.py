"""租户渠道组 SKU：分组 + 虚拟令牌（常见中转站形态）。

租户可管自己的组/令牌/限额；不能改平台渠道或全局熔断（仍走 /newapi 超管页）。
明文 Key 只在签发响应里出现一次，库内只存 hash。
"""
from sqlalchemy import (
    JSON, BigInteger, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import TenantMixin


class RelayGroup(TenantMixin, Base):
    """租户渠道组：模型名单 + RPM/TPM。"""

    __tablename__ = "relay_groups"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_relay_groups_tenant_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    name = Column(String(64), nullable=False, comment="组名，企业内唯一")
    rpm_limit = Column(Integer, nullable=False, default=0, server_default="0", comment="每分钟请求上限；0=不限")
    tpm_limit = Column(Integer, nullable=False, default=0, server_default="0", comment="每分钟 token 上限；0=不限")
    models_json = Column(JSON, nullable=True, comment="可用模型 id 列表；空=未限制")
    status = Column(String(16), nullable=False, default="enabled", server_default="enabled", comment="enabled/disabled")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")


class RelayToken(TenantMixin, Base):
    """租户虚拟令牌。key_hash 唯一；明文不落库。

    041 expand：gateway_key_id / spend_synced_at（ADR-0019 网关引用）。
    gateway_key_id NULL=040 骨架签发、从未登记网关的行；新签发必写。
    """

    __tablename__ = "relay_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    group_id = Column(Integer, ForeignKey("relay_groups.id"), nullable=False, comment="所属渠道组")
    name = Column(String(64), nullable=False, comment="令牌备注名")
    key_prefix = Column(String(16), nullable=False, comment="展示前缀 sk-…")
    key_hash = Column(String(64), nullable=False, unique=True, comment="SHA-256 指纹")
    quota_tokens = Column(Integer, nullable=False, default=-1, server_default="-1", comment="额度；-1=不限")
    used_tokens = Column(Integer, nullable=False, default=0, server_default="0", comment="已用 token")
    expires_at = Column(DateTime(timezone=True), nullable=True, comment="过期；空=不过期")
    revoked_at = Column(DateTime(timezone=True), nullable=True, comment="吊销时间")
    last_used_at = Column(DateTime(timezone=True), nullable=True, comment="最近使用")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    note = Column(Text, nullable=True, comment="备注")
    gateway_key_id = Column(
        String(191), nullable=True, unique=True,
        comment="LiteLLM 虚拟 Key 稳定引用（不透明）；NULL=骨架签发未登记网关。不是 DSN、不是 master",
    )
    spend_synced_at = Column(
        DateTime(), nullable=True,
        comment="最近一次网关 spend 回写 used_tokens 的时刻；NULL=从未同步",
    )
    blocked_reason = Column(
        String(32), nullable=True,
        comment="网关侧已 block 的原因 quota_exhausted/group_disabled/sku_expired/tenant_quota；NULL=未封（迁移 053）",
    )


class RelayUsageDaily(TenantMixin, Base):
    """中转令牌日粒度用量事实（审计 F3-9，迁移 053）

    由网关 spend 日志按日聚合写入；同一 (令牌, 日) 只增不减（取观察值与既有值的较大者），
    网关分页截断或日志清理不会让已记账的用量倒退。企业月度中转用量 = 本表按月求和。
    """

    __tablename__ = "relay_usage_daily"
    __table_args__ = (UniqueConstraint("token_id", "stat_date", name="uq_relay_usage_daily_token_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    token_id = Column(Integer, ForeignKey("relay_tokens.id", ondelete="CASCADE"), nullable=False,
                      index=True, comment="令牌")
    stat_date = Column(Date, nullable=False, comment="统计日（网关日志 startTime 所属的 Asia/Shanghai 业务日）")
    total_tokens = Column(BigInteger, nullable=False, default=0, server_default="0", comment="当日 token 合计")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
