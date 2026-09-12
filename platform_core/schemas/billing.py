"""计费契约：价目 / 订单 / 订阅。在线通道未开通。"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

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
    """订单读模型（GWT-50.3）：档位名称 + 状态 + 金额（用户可见=元，与定价页同一数字）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    amount_cents: int
    status: str
    channel: str
    paid_at: Optional[datetime] = None
    created_at: datetime
    tenant_id: Optional[int] = None
    plan_name: str = ""
    tenant_name: Optional[str] = None  # 超管运营台可见企业名（GWT-50.10）

    @computed_field  # type: ignore[prop-decorator]
    @property
    def amount_yuan(self) -> float:
        """用户可见金额（元）：amount_cents/100，免心算分（GWT-50.3，Q-PRICE 不撤 ¥299）。"""
        return round(self.amount_cents / 100, 2)


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    status: str
    current_period_end: Optional[datetime] = None
    tenant_id: Optional[int] = None
