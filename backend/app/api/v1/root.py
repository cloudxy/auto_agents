"""根路由 API"""
from fastapi import APIRouter
from platform_core.logger import get_logger

router = APIRouter()

@router.get("/")
async def root():
    """根路由"""
    logger = get_logger("api")
    logger.info("Root endpoint accessed")
    return {"message": "Auto Agents API is running"}