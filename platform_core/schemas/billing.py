"""计费契约：价目 / 订单 / 订阅。在线通道未开通。"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field
from platform_core.schemas.time_types import UTCDateTime

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
    # 决策 D17：按需定制、走「联系我们」的套餐（不能自助结账）
    sales_led: bool = False


class PlanGrantIn(BaseModel):
    """平台为定制客户开通套餐（决策 D17）：合同金额（分，整个合同期合计）+ 期数"""

    product: Literal["plan_enterprise", "plan_pro"] = "plan_enterprise"
    amount_cents: int = Field(..., ge=0, le=1_000_000_000, description="合同金额（分），记入订单")
    periods: int = Field(1, ge=1, le=36, description="开通几个账期（月付套餐 = 月数）")
    note: str = Field("", max_length=200, description="合同号等备注（记入产品事件与审计）")


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
    paid_at: Optional[UTCDateTime] = None
    created_at: UTCDateTime
    tenant_id: Optional[int] = None
    product_code: Optional[str] = None
    order_no: Optional[str] = None
    channel_trade_no: Optional[str] = None
    merchant_id_snapshot: Optional[str] = None
    fail_reason: Optional[str] = None
    late_notify_at: Optional[UTCDateTime] = None
    verified_at: Optional[UTCDateTime] = None
    fulfilled_at: Optional[UTCDateTime] = None
    unpaid_at: Optional[UTCDateTime] = None
    plan_name: str = ""
    tenant_name: Optional[str] = None  # 超管运营台可见企业名（GWT-50.10）
    # 在线支付真实网关产出（channel 已配商户凭据且网关调用成功时才有值；
    # 未配置/网关调用失败时为 None——照常走人工确认收款，不阻断下单）
    pay_url: Optional[str] = None       # 支付宝：可直接跳转的收银台链接
    qr_code_url: Optional[str] = None   # 微信：原始 code_url（复制链接用）
    qr_code_image: Optional[str] = None  # 微信：code_url 渲染的 SVG data URI，前端 <img src> 直接用

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
    current_period_end: Optional[UTCDateTime] = None
    tenant_id: Optional[int] = None
    # 决策 D22：用量页展示当前套餐、到期日与宽限截止
    plan_slug: Optional[str] = None
    plan_name: Optional[str] = None
    grace_until: Optional[UTCDateTime] = None
    in_grace: bool = False
