"""
外部 API 路由聚合器 - 专为第三方系统提供的 API 接口

职责：
- 聚合所有版本的外部 API 路由
- 管理外部 API 版本前缀
- 提供统一的外部 API 入口

与内部 API 的区别：
- 内部 API：/api/* - 用于管理后台、前端、内部服务
- 外部 API：/external/* - 用于第三方集成、开放平台、Webhook

安全特性：
- API Key 认证
- 请求签名验证
- 访问频率限制
- 详细的审计日志
"""
from fastapi import APIRouter

# 导入外部 API 各版本路由
from .v1 import router as v1_external_router

# 创建外部 API 路由器
external_api_router = APIRouter()

# 注册外部 API 各版本路由
external_api_router.include_router(v1_external_router, prefix="/v1")

__all__ = ["external_api_router"]
