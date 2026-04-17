"""参数基类 - 请求参数的公共基类

- QueryParams: GET 请求参数基类（自动 XSS 清理）
- RequestBody: POST/PUT 请求体基类（自动 XSS 清理）
- PaginationQuery: 分页查询参数（复用率高）
"""
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from backend.schemas.validators import sanitize_input


class QueryParams(BaseModel):
    """GET 请求查询参数基类
    
    所有字符串字段自动清理 XSS
    """
    
    @field_validator("*", mode="before")
    @classmethod
    def sanitize_strings(cls, v):
        if isinstance(v, str):
            return sanitize_input(v)
        return v


class PaginationQuery(QueryParams):
    """分页查询参数（复用率高）"""
    
    page: int = Field(1, ge=1, description="页码（从 1 开始）")
    page_size: int = Field(20, ge=1, le=100, description="每页大小（1-100）")


class RequestBody(BaseModel):
    """POST/PUT 请求体基类
    
    所有字符串字段自动清理 XSS
    """
    
    @field_validator("*", mode="before")
    @classmethod
    def sanitize_strings(cls, v):
        if isinstance(v, str):
            return sanitize_input(v)
        return v


class IdPathParams(BaseModel):
    """路径参数 - ID"""
    
    id: int = Field(..., gt=0, description="资源 ID")


class SlugPathParams(BaseModel):
    """路径参数 - Slug"""
    
    slug: str = Field(..., min_length=1, max_length=100, pattern=r'^[a-z0-9\-]+$', description="URL 友好标识")
