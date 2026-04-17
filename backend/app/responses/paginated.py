"""分页响应格式"""
from typing import Optional, Generic, TypeVar, List
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedData(BaseModel, Generic[T]):
    """分页数据结构"""
    
    items: List[T] = Field(..., description="数据列表")
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页大小")
    total_pages: int = Field(..., description="总页数")


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应格式"""
    
    success: bool = Field(..., description="请求是否成功")
    code: str = Field(..., description="业务状态码")
    message: str = Field(..., description="响应消息")
    data: Optional[PaginatedData[T]] = Field(None, description="分页数据")
    request_id: Optional[str] = Field(None, description="请求追踪 ID")
    
    @classmethod
    def success(
        cls,
        items: List[T],
        total: int,
        page: int,
        page_size: int,
        message: str = "查询成功",
        request_id: str = None
    ) -> "PaginatedResponse[T]":
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        
        return cls(
            success=True,
            code="SUCCESS",
            message=message,
            data=PaginatedData(
                items=items,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages
            ),
            request_id=request_id
        )
