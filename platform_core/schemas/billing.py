"""计费契约：价目 / 订单 / 订阅。在线通道未开通。"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

PayChannel = Literal["offline", "alipay", "wechat"]


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    price_cents: int
    period: str
    quota_json: Optional[str] = None
    is_public: int


class OrderCreate(BaseModel):
    plan_id: int
    channel: PayChannel = Field(default="offline")


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    amount_cents: int
    status: str
    channel: str
    paid_at: Optional[datetime] = None
    created_at: datetime
    tenant_id: Optional[int] = None


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    status: str
    current_period_end: Optional[datetime] = None
    tenant_id: Optional[int] = None
