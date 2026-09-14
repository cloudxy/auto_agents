"""能力市场读模型（T-21）：五类 listing，单体内域。

市场评分只许走 T-16 `POST /api/v1/skills/{name}/rescore`。
本包禁止直连网关 chat/admin，禁止新开评分链。
"""
from backend.services.power_market.service import PowerMarketService
from backend.services.power_market.store_page import STORE_NOT_FOUND_HTML
from backend.services.power_market.flag import (
    MARKET_CLOSED_CODE,
    MSG_EMPTY_SHELF,
    MSG_MARKET_CLOSED,
    is_power_market_enabled,
    set_power_market_enabled,
)
from backend.services.power_market.types import (
    HOST_LABELS,
    INVALID_ASSET_TYPE_MESSAGE,
    LEGACY_ASSET_TYPE_MAP,
    MARKET_COMING_SOON_CODE,
    MARKET_HOST_INCOMPAT_CODE,
    MARKET_NEEDS_TENANT_CODE,
    MARKET_NOT_FOUND_CODE,
    MARKET_READONLY_ROLE_CODE,
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
    PUBLIC_ASSET_TYPES,
    PUBLIC_HOSTS,
    READABLE_ASSET_TYPES,
    STORE_NOT_FOUND_COPY,
    STORE_NOT_FOUND_HOME,
    CorrectRequest,
    CreateSourceRequest,
    PatchLicenseOverrideRequest,
    PatchListingRequest,
    PutAliasRequest,
)

__all__ = [
    "HOST_LABELS",
    "INVALID_ASSET_TYPE_MESSAGE",
    "LEGACY_ASSET_TYPE_MAP",
    "MARKET_CLOSED_CODE",
    "MARKET_COMING_SOON_CODE",
    "MARKET_HOST_INCOMPAT_CODE",
    "MARKET_NEEDS_TENANT_CODE",
    "MARKET_NOT_FOUND_CODE",
    "MARKET_READONLY_ROLE_CODE",
    "MSG_EMPTY_SHELF",
    "MSG_MARKET_CLOSED",
    "is_power_market_enabled",
    "set_power_market_enabled",
    "PAGE_SIZE_DEFAULT",
    "PAGE_SIZE_MAX",
    "PUBLIC_ASSET_TYPES",
    "PUBLIC_HOSTS",
    "CorrectRequest",
    "CreateSourceRequest",
    "PatchLicenseOverrideRequest",
    "PatchListingRequest",
    "PutAliasRequest",
    "PowerMarketService",
    "READABLE_ASSET_TYPES",
    "STORE_NOT_FOUND_COPY",
    "STORE_NOT_FOUND_HOME",
    "STORE_NOT_FOUND_HTML",
]
