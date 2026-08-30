"""
API V1 版本路由聚合器

职责：
- 聚合 V1 版本的所有业务路由
- 定义 V1 版本的路由前缀和标签
"""
from fastapi import APIRouter
from . import root, health, spiders, admin, auth, configs, ai, llm_providers, newapi

router = APIRouter()

router.include_router(auth.router, tags=["认证"])
router.include_router(root.router, tags=["root"])
router.include_router(health.router, prefix="/health", tags=["health"])
router.include_router(spiders.router, prefix="/spiders", tags=["spiders"])
router.include_router(admin.router, prefix="/admin", tags=["admin"])
router.include_router(configs.router, prefix="/configs", tags=["configs"])
router.include_router(ai.router, prefix="/ai", tags=["ai"])
router.include_router(llm_providers.router, prefix="/llm", tags=["llm"])
router.include_router(newapi.router, prefix="/newapi", tags=["newapi"])

__all__ = ["router"]
