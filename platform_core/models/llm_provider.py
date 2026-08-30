"""LLM 供应商模型（阶段二：多供应商 DB 化管理 + 热切换）

多供应商注册表：API 层 CRUD / 连通性测试 / 单激活热切换；
ai_planner._llm_chat 经 LlmProviderService.resolve_runtime_config 消费：
激活且 enabled 的行优先，否则回退 config/default/llm.yml + .env（兜底路径行为不变）。

安全约定：
- api_key_encrypted 仅存 Fernet 密文（主密钥走 .env / 环境变量 LLM_ENCRYPTION_KEY，
  禁止写入任何 yml 或代码）；未配置主密钥时保存/更新带 api_key 的请求直接失败，
  不降级明文入库
- api_key 明文永不出服务层，API 响应一律输出掩码（见 schemas/llm_provider.py）
"""
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from platform_core.models.base import Base


class LlmProvider(Base):
    """LLM 供应商表（OpenAI 兼容协议为主，provider_type 预留扩展）"""

    __tablename__ = "llm_providers"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    name = Column(String(100), nullable=False, unique=True, index=True, comment="供应商名称（唯一）")
    provider_type = Column(String(50), nullable=False, default="openai_compatible",
                           server_default="openai_compatible",
                           comment="协议类型：openai_compatible（chat/completions）")
    base_url = Column(String(500), nullable=False, comment="API 基地址（http/https，如 https://api.openai.com/v1）")
    api_key_encrypted = Column(Text, nullable=True,
                               comment="Fernet 加密后的 API Key 密文（主密钥走 LLM_ENCRYPTION_KEY）")
    model = Column(String(100), nullable=False, comment="默认模型名（如 gpt-4o-mini）")
    temperature = Column(Float, nullable=False, default=0.2, server_default="0.2",
                         comment="采样温度（0-2）")
    timeout = Column(Integer, nullable=False, default=120, server_default="120",
                     comment="单次请求超时（秒）")
    max_retries = Column(Integer, nullable=False, default=3, server_default="3",
                         comment="指数退避重试次数")
    is_active = Column(Boolean, nullable=False, default=False, server_default="0",
                       comment="是否为当前激活供应商（全表至多一行，热切换用）")
    enabled = Column(Boolean, nullable=False, default=True, server_default="1",
                     comment="是否启用（禁用后即使激活也走 yml/env 兜底）")
    remark = Column(String(255), nullable=True, comment="备注")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(),
                        comment="更新时间")

    def __repr__(self) -> str:
        return f"<LlmProvider #{self.id} {self.name} active={self.is_active}>"
