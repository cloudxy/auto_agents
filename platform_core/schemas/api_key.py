from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from platform_core.schemas.time_types import UTCDateTime


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: Optional[str] = None
    expires_at: Optional[UTCDateTime] = None
    note: Optional[str] = None


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    key_prefix: str
    scopes: Optional[str] = None
    expires_at: Optional[UTCDateTime] = None
    revoked_at: Optional[UTCDateTime] = None
    last_used_at: Optional[UTCDateTime] = None
    created_at: UTCDateTime
    tenant_id: Optional[int] = None


class ApiKeyCreated(ApiKeyOut):
    """仅创建响应携带一次明文。"""

    plaintext: str
