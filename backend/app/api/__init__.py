"""
API 路由聚合器 - 统一管理所有版本的 API 路由

职责：
- 聚合各版本 API 路由
- 管理路由版本前缀
- 提供统一的路由入口

版本说明：
- api/v1/ - 当前稳定版本
- api/v2/ - 增强版本（已实现）
- api/v3/ - 未来版本（待开发）
"""
from fastapi import APIRouter

# 创建主 API 路由器
api_router = APIRouter()

# 导入各版本路由
from .v1 import router as v1_router
from .v2 import router as v2_router

# 注册各版本路由
api_router.include_router(v1_router, prefix="/v1")
api_router.include_router(v2_router, prefix="/v2")

__all__ = ["api_router"]
