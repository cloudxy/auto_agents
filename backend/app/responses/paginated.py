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
    """分页响应信封（data 为 PaginatedData；ADR-001 分页端点统一载体）

    注意：不要在此类上定义与字段同名的 classmethod（历史上 `success` 方法与
    `success: bool` 字段重名，Pydantic 会把 bound method 当字段默认值并污染
    OpenAPI schema）；构造请用模块级 `paginated()` / `paginated_from_offset()`。
    """

    success: bool = Field(..., description="请求是否成功")
    code: str = Field(..., description="业务状态码")
    message: str = Field(..., description="响应消息")
    data: Optional[PaginatedData[T]] = Field(None, description="分页数据")
    request_id: Optional[str] = Field(None, description="请求追踪 ID")


def paginated(
    items: List[T],
    total: int,
    page: int,
    page_size: int,
    message: str = "查询成功",
    request_id: Optional[str] = None,
) -> PaginatedResponse[T]:
    """分页信封构造（page/page_size 型端点直接用）"""
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    return PaginatedResponse(
        success=True,
        code="SUCCESS",
        message=message,
        data=PaginatedData(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
        request_id=request_id,
    )


def paginated_from_offset(
    items: List[T],
    total: int,
    skip: int,
    limit: int,
    message: str = "查询成功",
) -> PaginatedResponse[T]:
    """offset/limit 分页端点的便捷构造（page 由 skip // limit + 1 换算）"""
    page = (skip // limit) + 1 if limit > 0 else 1
    return paginated(
        items=items, total=total, page=page, page_size=limit, message=message
    )
