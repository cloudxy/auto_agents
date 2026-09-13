"""夹具企业名单契约（Router/Service 边界；禁止 import ORM）"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InternalFixtureTenantCreate(BaseModel):
    tenant_id: int = Field(..., ge=1)


class InternalFixtureTenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    created_by: str
    created_at: datetime
    updated_at: datetime


class InternalFixtureTenantListOut(BaseModel):
    total: int
    items: list[InternalFixtureTenantOut]
