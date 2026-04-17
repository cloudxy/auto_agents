"""根路由 API"""
from fastapi import APIRouter
from platform_core.infra.log_init import get_logger

router = APIRouter()

@router.get("/")
async def root():
    """根路由"""
    logger = get_logger("api")
    logger.info("Root endpoint accessed")
    return {"message": "Auto Agents API is running"}

@router.get("/health")
async def health():
    """基础健康检查"""
    return {"status": "healthy"}