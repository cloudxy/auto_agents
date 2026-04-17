"""统一 API 响应格式"""
from typing import Optional, Any, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应格式"""
    
    success: bool = Field(..., description="请求是否成功")
    code: str = Field(..., description="业务状态码")
    message: str = Field(..., description="响应消息")
    data: Optional[T] = Field(None, description="响应数据")
    request_id: Optional[str] = Field(None, description="请求追踪 ID")
    
    @classmethod
    def success(
        cls,
        data: T = None,
        message: str = "操作成功",
        code: str = "SUCCESS",
        request_id: str = None
    ) -> "ApiResponse[T]":
        return cls(success=True, code=code, message=message, data=data, request_id=request_id)
    
    @classmethod
    def error(
        cls,
        message: str = "操作失败",
        code: str = "ERROR",
        data: Any = None,
        request_id: str = None
    ) -> "ApiResponse[None]":
        return cls(success=False, code=code, message=message, data=data, request_id=request_id)


def ok(data: Any = None, message: str = "操作成功") -> ApiResponse:
    """快捷创建成功响应"""
    return ApiResponse.success(data=data, message=message)


def created(data: Any = None, message: str = "创建成功") -> ApiResponse:
    return ApiResponse.success(data=data, message=message, code="CREATED")


def updated(data: Any = None, message: str = "更新成功") -> ApiResponse:
    return ApiResponse.success(data=data, message=message, code="UPDATED")


def deleted(message: str = "删除成功") -> ApiResponse:
    return ApiResponse.success(data=None, message=message, code="DELETED")
