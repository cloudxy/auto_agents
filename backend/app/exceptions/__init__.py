"""统一异常处理 - 导出所有异常类和处理器

使用方式：
    from backend.app.exceptions import BusinessException, NotFoundException
    from backend.app.exceptions import register_exception_handlers
"""
from backend.app.exceptions.base import AppException
from backend.app.exceptions.business import (
    BusinessException,
    AuthenticationException,
    AuthorizationException,
    NotFoundException,
    ValidationException,
    RateLimitException,
    DatabaseException,
)
from backend.app.exceptions.handlers import register_exception_handlers

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
