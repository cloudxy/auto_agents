"""公开五类枚举 + expand 双值（一周期 expert/expert_team 可读）。"""
from typing import Optional

from pydantic import BaseModel, model_validator

PUBLIC_ASSET_TYPES: tuple[str, ...] = (
    "skill", "plugin", "command", "agent", "team",
)
LEGACY_ASSET_TYPE_MAP: dict[str, str] = {
    "expert": "agent",
    "expert_team": "team",
}
READABLE_ASSET_TYPES: tuple[str, ...] = PUBLIC_ASSET_TYPES + tuple(
    LEGACY_ASSET_TYPE_MAP.keys()
)
INVALID_ASSET_TYPE_MESSAGE = "没有这种类型"

LISTING_VISIBLE: tuple[str, ...] = ("listed", "coming_soon")
GOVERNANCE_PUBLIC: tuple[str, ...] = ("stable", "recommended")
# T-31：默认允许集 + assets.public_license_override；不建许可表。
DEFAULT_ALLOWED_LICENSES: tuple[str, ...] = (
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "CC0-1.0", "Unlicense",
)
PUBLIC_HOSTS: tuple[str, ...] = ("grok", "zcode", "kimi", "claude")
HOST_LABELS: dict[str, str] = {
    "grok": "Grok", "zcode": "ZCode", "kimi": "Kimi", "claude": "Claude",
}
PAGE_SIZE_DEFAULT = 20
# T-14（FR-81/NFR-02）：公开端页大小上限收到 20（此前 50）。
# 该常量只被公开两端（/public/skills、/public/capabilities）消费，无管理端分闸需求。
PAGE_SIZE_MAX = 20
# T-13（FR-80）：公开商店测试种子谓词三支（与 GWT-80.1 同口径；PIT-5 双公开端共享）
SEED_NAME_PREFIX = "nfr01qc2-"
SEED_TITLE_PREFIX = "NFR卡片"
SEED_DESC_MARKER = "preprod nfr-01 seed"
STORE_NOT_FOUND_COPY = "页面不存在，可能已被移除或地址有误"
STORE_NOT_FOUND_HOME = "返回首页"
MARKET_NOT_FOUND_CODE = "MARKET_NOT_FOUND"
MARKET_COMING_SOON_CODE = "MARKET_COMING_SOON"
MARKET_HOST_INCOMPAT_CODE = "MARKET_HOST_INCOMPAT"
MARKET_READONLY_ROLE_CODE = "MARKET_READONLY_ROLE"
MARKET_NEEDS_TENANT_CODE = "MARKET_NEEDS_TENANT"
MSG_READONLY_ROLE = "当前账号不能订阅，请联系企业管理员"
MSG_INSTALL_READONLY = "当前账号不能改安装。请联系企业管理员。"
MSG_NEEDS_TENANT = "需要企业空间才能订阅"
MSG_NOT_FOUND = "没有这个能力，不能订阅。"
MSG_COMING_SOON = "这是预告项，现在不能订阅。"
MSG_ALREADY_SUBSCRIBED = "已订阅到 {host}，没有新增行。"
MSG_SUBSCRIBED = "已订阅到 {host}"
MSG_FLAGS_LOCKED = "该安装行不能改启用或信任。"
MSG_DELISTED = "已下架"
MSG_DELISTED_RESUBSCRIBE = "已下架，不能新订"
REF_SKIP_ACTION = "market.ref.skip"
REF_SKIP_BLACKLIST = "blacklist"
REF_SKIP_DELETED = "deleted"


class SubscribeRequest(BaseModel):
    host: Optional[str] = None


LISTING_STATES: tuple[str, ...] = ("unlisted", "listed", "coming_soon")
MERGED_PLUGIN_NAME = "dev-team"
FIRST_PARTY_SOURCE = "self_built"
MSG_LISTING_MERGED = "已合并，不可上架"
MSG_LISTING_BLACKLIST = "黑名单资产不能上架"
MSG_LISTING_CONFIRM = "将把第三方「{name}」标为已上架，商店会对访客可见。确认上架？"
LISTING_CONFIRM_CODE = "LISTING_CONFIRM_REQUIRED"
LISTING_MERGED_CODE = "LISTING_MERGED"
LISTING_BLACKLIST_CODE = "LISTING_BLACKLIST"
SOURCE_KINDS: tuple[str, ...] = ("local", "git", "url")
SOURCE_KIND_CODE = "SOURCE_KIND_UNSUPPORTED"
MSG_URL_UNSUPPORTED = "网址类源尚未支持，不能创建，不会开始爬取"
MSG_GIT_UNSUPPORTED = "git 类源尚未支持，不能创建，不会开始爬取"
CORRECT_THIRD_PARTY_CODE = "CORRECT_THIRD_PARTY"
MSG_CORRECT_THIRD_PARTY = "纠正对该行不可用（第三方只能写库内，不写源树）"
SYNC_IN_PROGRESS_CODE = "SYNC_IN_PROGRESS"
PLUGIN_COLLISION_CODE = "PLUGIN_NAME_COLLISION"
MSG_PLUGIN_COLLISION = "插件目录名已存在，禁止静默改名"
ALIAS_CONFLICT_CODE = "ALIAS_CONFLICT"
MSG_ALIAS_CONFLICT = "该短名已被占用，两边都未改动"


class CreateSourceRequest(BaseModel):
    name: str
    source_kind: str
    uri: str
    is_enabled: int = 1


class CorrectRequest(BaseModel):
    category: Optional[str] = None
    status: Optional[str] = None
    score: Optional[float] = None


class PatchListingRequest(BaseModel):
    listing_state: str
    confirm: bool = False


class PutAliasRequest(BaseModel):
    slug: str

    @model_validator(mode="after")
    def slug_len(self):
        slug = (self.slug or "").strip()
        if not slug or len(slug) > 128:
            raise ValueError("slug 长度 1–128")
        self.slug = slug
        return self


class PatchLicenseOverrideRequest(BaseModel):
    public_license_override: int

    @model_validator(mode="after")
    def flag_01(self):
        if self.public_license_override not in (0, 1):
            raise ValueError("public_license_override 只能是 0 或 1")
        return self


class PatchInstallRequest(BaseModel):
    enabled: Optional[int] = None
    trusted: Optional[int] = None

    @model_validator(mode="after")
    def need_flag(self):
        if self.enabled is None and self.trusted is None:
            raise ValueError("enabled 或 trusted 至少填一项")
        for field, value in (("enabled", self.enabled), ("trusted", self.trusted)):
            if value is not None and value not in (0, 1):
                raise ValueError(f"{field} 只能是 0 或 1")
        return self


def _to_public_asset_type(stored: str) -> str:
    return LEGACY_ASSET_TYPE_MAP.get(stored, stored)


def _stored_types_for(public_type: str) -> tuple[str, ...]:
    legacy = tuple(k for k, v in LEGACY_ASSET_TYPE_MAP.items() if v == public_type)
    return (public_type,) + legacy
