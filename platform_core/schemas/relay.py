"""租户渠道组 / 令牌契约。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RelayGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    rpm_limit: int = 0
    tpm_limit: int = 0
    models: list[str] = Field(default_factory=list)


class RelayGroupUpdate(BaseModel):
    name: Optional[str] = None
    rpm_limit: Optional[int] = None
    tpm_limit: Optional[int] = None
    models: Optional[list[str]] = None
    status: Optional[str] = None


class RelayGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    rpm_limit: int
    tpm_limit: int
    models: list[str] = Field(default_factory=list)
    status: str
    tenant_id: Optional[int] = None
    created_at: datetime


class RelayTokenCreate(BaseModel):
    group_id: int
    name: str = Field(min_length=1, max_length=64)
    quota_tokens: int = -1


class RelayTokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    name: str
    key_prefix: str
    quota_tokens: int
    used_tokens: int
    status: str
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime
    plaintext_key: Optional[str] = None


class RelayUpgradeOut(BaseModel):
    action: str
    product: str
    checkout_path: Optional[str] = None
    message: str


class RelaySkuPageOut(BaseModel):
    """「我的渠道组」SKU 闸读模型。status 来自权益表，不是组行 COUNT。"""

    status: str
    period_end: Optional[datetime] = None
    can_issue: bool
    empty_title: str = ""
    empty_hint: str = ""
    upgrade: Optional[RelayUpgradeOut] = None
