"""异常基类 - 所有自定义异常的父类"""
from typing import Optional


class AppException(Exception):
    """应用异常基类（所有自定义异常的父类）
    
    继承树：
    AppException
    ├── BusinessException        (400)
    ├── AuthenticationException  (401)
    ├── AuthorizationException   (403)
    ├── NotFoundException        (404)
    ├── ValidationException      (422)
    ├── RateLimitException       (429)
    └── DatabaseException        (500)
    """
    
    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = 400,
        data: Optional[dict] = None
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.data = data or {}
        super().__init__(self.message)
