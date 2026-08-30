"""统一参数接收器 - 导出所有 Schema 类和验证器

使用方式：
    from platform_core.schemas import LoginRequest, RegisterRequest, PaginationQuery
    from platform_core.schemas import validate_email, validate_phone
"""
from platform_core.schemas.base import (
    QueryParams,
    RequestBody,
    PaginationQuery,
    IdPathParams,
    SlugPathParams,
)
from platform_core.schemas.validators import (
    validate_email,
    validate_phone,
    validate_string_length,
    sanitize_input,
)
from platform_core.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    UpdatePasswordRequest,
)
from platform_core.schemas.spider import (
    SpiderTaskResponse,
    SpiderTaskListResponse,
    SpiderTaskQuery,
    RunSpiderRequest,
    SpiderResultResponse,
    SpiderResultListResponse,
    SpiderStatsResponse,
)
from platform_core.schemas.ai_plan import (
    FlowConfig,
    SelectorRule,
    PaginationConfig,
    DetailConfig,
    FilterRule,
    AiPlanCreate,
    AiPlanResponse,
    AiPlanListResponse,
    validate_selector_expr,
)
from platform_core.schemas.newapi import (
    ProbeVerdict,
    ChannelEventAction,
    ChannelEventSource,
    ChannelEventResponse,
    ChannelEventListResponse,
    ChannelProbeResultResponse,
    ChannelProbeResultListResponse,
)

__all__ = [
    # 基类
    "QueryParams",
    "RequestBody",
    "PaginationQuery",
    "IdPathParams",
    "SlugPathParams",
    # 验证器
    "validate_email",
    "validate_phone",
    "validate_string_length",
    "sanitize_input",
    # 认证 Schema
    "LoginRequest",
    "RegisterRequest",
    "UpdatePasswordRequest",
    # 爬虫任务 Schema
    "SpiderTaskResponse",
    "SpiderTaskListResponse",
    "SpiderTaskQuery",
    "RunSpiderRequest",
    "SpiderResultResponse",
    "SpiderResultListResponse",
    "SpiderStatsResponse",
    # AI 采集计划 Schema（阶段二）
    "FlowConfig",
    "SelectorRule",
    "PaginationConfig",
    "DetailConfig",
    "FilterRule",
    "AiPlanCreate",
    "AiPlanResponse",
    "AiPlanListResponse",
    "validate_selector_expr",
    # new-api 渠道集成 Schema（阶段三）
    "ProbeVerdict",
    "ChannelEventAction",
    "ChannelEventSource",
    "ChannelEventResponse",
    "ChannelEventListResponse",
    "ChannelProbeResultResponse",
    "ChannelProbeResultListResponse",
]
