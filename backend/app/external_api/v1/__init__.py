"""
外部 API V1 版本路由聚合器

职责：
- 聚合 V1 版本的所有外部业务路由
- 定义外部 API 的路由前缀和标签

外部 API 特点：
- 需要认证（API Key / Signature）
- 限流保护
- 详细的访问日志
- 稳定的接口契约
"""
from fastapi import APIRouter
from . import webhooks, public

# 创建外部 API V1 路由器
router = APIRouter()

# 注册 V1 版本的子路由
router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
router.include_router(public.router, prefix="/public", tags=["public"])

__all__ = ["router"]
