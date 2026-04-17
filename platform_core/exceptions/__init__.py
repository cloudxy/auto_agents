"""统一异常处理 - 导出所有异常类和处理器

使用方式：
    from platform_core.exceptions import BusinessException, NotFoundException
    from platform_core.exceptions import register_exception_handlers
"""
from platform_core.exceptions.base import AppException
from platform_core.exceptions.business import (
    BusinessException,
    AuthenticationException,
    AuthorizationException,
    NotFoundException,
    ValidationException,
    RateLimitException,
    DatabaseException,
)
from platform_core.exceptions.handlers import register_exception_handlers

__all__ = [
    # 基类
    "AppException",
    # 业务异常
    "BusinessException",
    "AuthenticationException",
    "AuthorizationException",
    "NotFoundException",
    "ValidationException",
    "RateLimitException",
    "DatabaseException",
    # 处理器注册
    "register_exception_handlers",
]
