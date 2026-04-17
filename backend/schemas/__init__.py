"""统一参数接收器 - 导出所有 Schema 类和验证器

使用方式：
    from backend.schemas import LoginRequest, RegisterRequest, PaginationQuery
    from backend.schemas import validate_email, validate_phone
"""
from backend.schemas.base import (
    QueryParams,
    RequestBody,
    PaginationQuery,
    IdPathParams,
    SlugPathParams,
)
from backend.schemas.validators import (
    validate_email,
    validate_phone,
    validate_string_length,
    sanitize_input,
)
from backend.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    UpdatePasswordRequest,
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
]
