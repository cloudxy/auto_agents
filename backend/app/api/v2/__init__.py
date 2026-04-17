"""
API V2 版本路由聚合器

职责：
- 聚合 V2 版本的所有业务路由
- 定义 V2 版本的路由前缀和标签

V2 已实现特性：
- 增强的健康检查（包含响应时间监控）
- 数据库连接状态检测（MySQL + Redis）
- 存储系统健康检查
- 版本信息接口

当前路由：
- GET / - 版本信息
- GET /health/ - 基础健康检查（含响应时间）
- GET /health/db - 数据库健康检查
- GET /health/storage - 存储系统健康检查
"""
from fastapi import APIRouter
from . import root, health

# 创建 V2 版本路由器
router = APIRouter()

# 注册 V2 版本的子路由
router.include_router(root.router, tags=["root"])
router.include_router(health.router, prefix="/health", tags=["health"])

__all__ = ["router"]
