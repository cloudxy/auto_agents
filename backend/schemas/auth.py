"""认证相关 Schema - 登录、注册等请求参数"""
from pydantic import Field, field_validator
from backend.schemas.base import RequestBody
from backend.schemas.validators import validate_email


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
