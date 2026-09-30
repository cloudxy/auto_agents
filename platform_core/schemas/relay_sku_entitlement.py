"""中转 SKU 权益契约。缺行 ≡ none；本文件不写开通 HTTP。"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from platform_core.schemas.time_types import UTCDateTime

RelaySkuStatus = Literal["none", "active", "expired"]


class RelaySkuEntitlementCreate(BaseModel):
    tenant_id: int = Field(..., ge=1)
    status: RelaySkuStatus = "none"
    period_end: Optional[UTCDateTime] = None
    activated_at: Optional[UTCDateTime] = None


class RelaySkuEntitlementUpdate(BaseModel):
    status: Optional[RelaySkuStatus] = None
    period_end: Optional[UTCDateTime] = None
    activated_at: Optional[UTCDateTime] = None


class RelaySkuEntitlementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    status: str
    period_end: Optional[UTCDateTime] = None
    activated_at: Optional[UTCDateTime] = None
    created_at: UTCDateTime
    updated_at: UTCDateTime
