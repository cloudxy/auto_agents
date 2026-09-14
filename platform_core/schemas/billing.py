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


CheckoutProduct = Literal["plan_pro", "plan_enterprise", "relay"]
OnlinePayChannel = Literal["alipay", "wechat"]


class CheckoutCreate(BaseModel):
    product: CheckoutProduct
    channel: Optional[OnlinePayChannel] = None


class OrderConfirmIn(BaseModel):
    """超管确认收款。order_id 若出现必须等于路径 id（GWT-M31.5）。"""

    order_id: Optional[int] = None


class CheckoutChannelView(BaseModel):
    channel: OnlinePayChannel
    configured: bool
    selectable: bool


class CheckoutPreviewOut(BaseModel):
    product: CheckoutProduct
    channels: list[CheckoutChannelView]
    empty_state: Optional[str] = None
    can_pay: bool = False
    order_id: Optional[int] = None
    amount_cents: Optional[int] = None
    notice: Optional[str] = None


class ChannelNotifyIn(BaseModel):
    """通道通知体。缺校验字段由服务层当未验真（HTTP 仍 200）。"""

    model_config = ConfigDict(extra="allow")

    order_no: Optional[str] = None
    merchant_no: Optional[str] = None
    amount_cents: Optional[int] = None
    trade_status: Optional[str] = None
    channel_trade_no: Optional[str] = None
    sign: Optional[str] = None


class OrderOut(BaseModel):
    """订单读模型（GWT-50.3）：档位名称 + 状态 + 金额（用户可见=元，与定价页同一数字）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: Optional[int] = None
    amount_cents: int
    status: str
    channel: Optional[str] = None
    paid_at: Optional[datetime] = None
    created_at: datetime
    tenant_id: Optional[int] = None
    product_code: Optional[str] = None
    order_no: Optional[str] = None
    channel_trade_no: Optional[str] = None
    merchant_id_snapshot: Optional[str] = None
    fail_reason: Optional[str] = None
    late_notify_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    fulfilled_at: Optional[datetime] = None
    unpaid_at: Optional[datetime] = None
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
