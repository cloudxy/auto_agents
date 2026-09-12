"""出站拉数钥匙契约（FR-51 / ADR-0020）。

明文只在签发响应（plaintext_key）出现一次；列表/详情只回前缀与派生状态。
产品名统一「出站拉数钥匙」；与渠道组令牌（sk-）互不相干。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class OutboundKeyCreate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=64)


class OutboundKeyOut(BaseModel):
    """列表/详情行：只见前缀与状态（GWT-51.8），不见明文。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Optional[str] = None
    key_prefix: str
    status: str = Field(description="active=已签发；revoked=已吊销（revoked_at 派生）")
    revoked_at: Optional[datetime] = None
    created_at: datetime


class OutboundKeyIssuedOut(OutboundKeyOut):
    """签发响应：明文只回这一次。"""

    plaintext_key: str = Field(description="明文钥匙；仅签发响应返回一次，库内只存 hash")
