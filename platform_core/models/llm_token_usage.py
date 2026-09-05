"""LLM token 用量模型 - 按供应商/模型/日聚合（P0-3 用量持久化）"""
from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from platform_core.models.base import Base
from platform_core.models.mixins import TenantMixin


class LlmTokenUsage(TenantMixin, Base):
    """LLM token 用量日聚合表

    写入路径：llm_client 每次调用成功 → Redis 日/月计数（llm_usage_service）
    → LlmUsageFlushService 定时聚合 upsert 落库。

    维度约定：
    - provider_name 存用量维度标识："provider:<id>" 或 "config"（yml/env 兜底路径），
      与 llm_client 的 usage_dim 同源；冗余存名保证 provider 删除后历史用量不失义
    - provider_id 仅作展示辅助（兜底路径为 NULL），不参与唯一约束
    """
    __tablename__ = "llm_token_usage"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_name", "model", "stat_date", name="uq_llm_usage_dim"),
    )

    id = Column(Integer, primary_key=True, comment="ID")
    provider_id = Column(Integer, ForeignKey("llm_providers.id"), nullable=True,
                         comment="供应商 ID（兜底路径为 NULL）")
    provider_name = Column(String(64), nullable=False, index=True, comment="用量维度：provider:<id> 或 config")
    model = Column(String(128), nullable=False, comment="模型名")
    stat_date = Column(Date, nullable=False, comment="统计日期")
    prompt_tokens = Column(BigInteger, nullable=False, default=0, server_default="0", comment="提示 token 累计")
    completion_tokens = Column(BigInteger, nullable=False, default=0, server_default="0", comment="补全 token 累计")
    total_tokens = Column(BigInteger, nullable=False, default=0, server_default="0", comment="总 token 累计")
    request_count = Column(Integer, nullable=False, default=0, server_default="0", comment="成功请求数")
    failed_count = Column(Integer, nullable=False, default=0, server_default="0", comment="失败请求数")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    def __repr__(self):
        return f"<LlmTokenUsage {self.provider_name}/{self.model} {self.stat_date}>"
