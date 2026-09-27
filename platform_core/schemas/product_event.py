"""产品事件契约（Router/Service 边界；禁止 import ORM）"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

PUBLIC_EVENT_NAMES = ("official_page_viewed", "official_cta_clicked")
CTA_FUNNEL = ("register_free", "pricing_pro", "pricing_enterprise", "login", "browse_market")
CTA_BYPASS = ("enter_admin", "try_ai_flow")
MARKET_EVENT_NAMES = (
    "market_subscribe_succeeded",
    "market_subscribe_rejected",
    "market_list_viewed",
    "market_search_submitted",
    "market_detail_viewed",
    "market_uninstalled",
    "market_listing_changed",
    "market_source_sync_completed",
)
WAVE0_EVENT_NAMES = (
    "official_page_viewed",
    "official_cta_clicked",
    "tenant_signup_succeeded",
    "login_succeeded",
    "login_failed",
    "task_run_submitted",
    "task_completed",
    "task_blocked",
    "results_exported",
    "quota_exceeded",
    "llm_planning_blocked",
    "data_export_completed",
    "checkout_story_started",
    "order_status_reached",
    "second_checkout_story_submitted",
    "outbound_wrong_plane_rejected",
    "duty_entry_opened",
)
LOGIN_FAIL_REASONS = ("credential", "expired", "locked")
QUOTA_DIMENSIONS = ("concurrency", "storage", "llm_tokens")
_SECRET_PROP_KEYS = frozenset({"password", "admin_password", "token", "access_token"})


def strip_secret_props(props: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not props:
        return props
    return {k: v for k, v in props.items() if k not in _SECRET_PROP_KEYS}


class PublicEventIn(BaseModel):
    """官网无鉴权埋点（仅页浏览 / CTA；失败由服务层吞掉）"""

    event_name: Literal["official_page_viewed", "official_cta_clicked"]
    anonymous_id: str = Field(..., min_length=1, max_length=64)
    occurred_at: Optional[datetime] = None
    props: Optional[dict[str, Any]] = None

    @field_validator("props")
    @classmethod
    def _no_secrets(cls, v: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        return strip_secret_props(v)


class ProductEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    event_name: str
    tenant_id: Optional[int] = None
    actor_user_id: Optional[int] = None
    anonymous_id: Optional[str] = None
    role: Optional[str] = None
    props: Optional[dict[str, Any]] = None
    created_at: datetime
    is_internal_fixture: Optional[bool] = None


class ProductEventListOut(BaseModel):
    total: int
    items: list[ProductEventOut]
    timezone: str = "Asia/Shanghai"
