"""中转 SKU 权益契约。缺行 ≡ none；本文件不写开通 HTTP。"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

RelaySkuStatus = Literal["none", "active", "expired"]


class RelaySkuEntitlementCreate(BaseModel):
    tenant_id: int = Field(..., ge=1)
    status: RelaySkuStatus = "none"
    period_end: Optional[datetime] = None
    activated_at: Optional[datetime] = None


class RelaySkuEntitlementUpdate(BaseModel):
    status: Optional[RelaySkuStatus] = None
    period_end: Optional[datetime] = None
    activated_at: Optional[datetime] = None


class RelaySkuEntitlementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    status: str
    period_end: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
