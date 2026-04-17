"""统一响应格式 - 导出所有响应类和快捷函数

使用方式：
    from backend.app.responses import ApiResponse, PaginatedResponse, ok, created
"""
from backend.app.responses.api import (
    ApiResponse,
    ok,
    created,
    updated,
    deleted,
)
from backend.app.responses.paginated import (
    PaginatedData,
    PaginatedResponse,
)

__all__ = [
    # API 响应
    "ApiResponse",
    "ok",
    "created",
    "updated",
    "deleted",
    # 分页响应
    "PaginatedData",
    "PaginatedResponse",
]
