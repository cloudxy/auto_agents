"""认证相关 Schema - 登录、注册等请求参数"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from platform_core.schemas.base import RequestBody
from platform_core.schemas.validators import validate_email


class LoginRequest(RequestBody):
    """登录请求"""
    
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")


class RegisterRequest(RequestBody):
    """注册请求"""
    
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: str = Field(..., description="邮箱")
    password: str = Field(..., min_length=8, max_length=128, description="密码（至少8位）")
    
    @field_validator("email")
    @classmethod
    def check_email(cls, v):
        return validate_email(v)


class UpdatePasswordRequest(RequestBody):
    """修改密码请求"""
    
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=8, max_length=128, description="新密码（至少8位）")


class UserResponse(BaseModel):
    """用户信息对外响应（不含密码哈希）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    is_active: bool = True
    is_admin: bool = False
    role: str = "operator"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class UserListResponse(BaseModel):
    """用户分页列表响应"""
    total: int
    items: List[UserResponse]


class OperationLogResponse(BaseModel):
    """操作审计日志响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: Optional[int] = None
    actor_name: str
    action: str
    target: str
    detail: Optional[str] = None
    created_at: Optional[datetime] = None

