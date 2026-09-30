"""夹具企业名单契约（Router/Service 边界；禁止 import ORM）"""

from pydantic import BaseModel, ConfigDict, Field
from platform_core.schemas.time_types import UTCDateTime


class InternalFixtureTenantCreate(BaseModel):
    tenant_id: int = Field(..., ge=1)


class InternalFixtureTenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    created_by: str
    created_at: UTCDateTime
    updated_at: UTCDateTime


class InternalFixtureTenantListOut(BaseModel):
    total: int
    items: list[InternalFixtureTenantOut]
