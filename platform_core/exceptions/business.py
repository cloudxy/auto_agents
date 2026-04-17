"""业务异常类 - 常见业务场景的预定义异常"""
from platform_core.exceptions.base import AppException


class BusinessException(AppException):
    """业务逻辑异常（默认 400）
    
    用途：通用业务规则违反
    示例：用户名已存在、订单数量不合法
    """
    
    def __init__(self, message: str = "业务处理失败", code: str = "BUSINESS_ERROR", status_code: int = 400, data=None):
        super().__init__(message=message, code=code, status_code=status_code, data=data)


class AuthenticationException(AppException):
    """认证失败异常（401）
    
    用途：Token 过期、密码错误、未登录
    """
    
    def __init__(self, message: str = "认证失败", code: str = "AUTH_FAILED"):
        super().__init__(message=message, code=code, status_code=401)


class AuthorizationException(AppException):
    """授权失败异常（403）
    
    用途：权限不足、角色不匹配
    """
    
    def __init__(self, message: str = "权限不足", code: str = "FORBIDDEN"):
        super().__init__(message=message, code=code, status_code=403)


class NotFoundException(AppException):
    """资源不存在异常（404）
    
    用途：查询的资源不存在
    """
    
    def __init__(self, resource: str = "资源", code: str = "NOT_FOUND"):
        super().__init__(
            message=f"{resource}不存在",
            code=code,
            status_code=404
        )


class ValidationException(AppException):
    """参数验证异常（422）
    
    用途：参数格式不正确、超出范围
    """
    
    def __init__(self, message: str, field: str, code: str = "VALIDATION_ERROR"):
        super().__init__(
            message=message,
            code=code,
            status_code=422,
            data={"field": field}
        )


class RateLimitException(AppException):
    """频率限制异常（429）
    
    用途：请求过于频繁、超过配额
    """
    
    def __init__(self, message: str = "请求过于频繁", retry_after: int = 60):
        super().__init__(
            message=message,
            code="RATE_LIMITED",
            status_code=429,
            data={"retry_after": retry_after}
        )


class DatabaseException(AppException):
    """数据库操作异常（500）
    
    用途：SQL 执行失败、连接超时
    """
    
    def __init__(self, message: str = "数据库操作失败"):
        super().__init__(
            message=message,
            code="DATABASE_ERROR",
            status_code=500
        )
