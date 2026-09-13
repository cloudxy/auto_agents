"""商户凭据契约。HTTP 读回无密文全文；Put.secrets 仅写入。"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

PaymentChannel = Literal["alipay", "wechat"]
SECRETS_MASK = "********"


class PaymentChannelCredentialCreate(BaseModel):
    channel: PaymentChannel
    merchant_no: str = Field(..., min_length=1, max_length=64)
    secrets_encrypted: str = Field(..., min_length=1)


class PaymentChannelCredentialUpdate(BaseModel):
    merchant_no: Optional[str] = Field(default=None, min_length=1, max_length=64)
    secrets_encrypted: Optional[str] = Field(default=None, min_length=1)
    updated_by: Optional[str] = None


class PaymentChannelCredentialPut(BaseModel):
    """超管保存/轮换：secrets 为明文整包，服务端 Fernet 后落库。"""

    channel: PaymentChannel
    merchant_no: str = Field(..., min_length=1, max_length=64)
    secrets: str = Field(..., min_length=1, max_length=16384)


class PaymentChannelCredentialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel: str
    merchant_no: str
    key_version: int
    rotated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PaymentChannelCredentialView(BaseModel):
    """超管读回：密钥只见掩码。未配置行可填空表单。"""

    channel: PaymentChannel
    configured: bool
    merchant_no: Optional[str] = None
    secrets_masked: Optional[str] = None
    key_version: Optional[int] = None
    rotated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PaymentChannelCredentialListOut(BaseModel):
    channels: list[PaymentChannelCredentialView]
