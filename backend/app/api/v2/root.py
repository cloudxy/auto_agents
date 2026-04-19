"""V2 根路由 - 展示与 V1 的差异"""
from fastapi import APIRouter
from platform_core.logger import get_logger

router = APIRouter()

@router.get("/")
async def root():
    """V2 根路由 - 返回版本信息"""
    logger = get_logger("api")
    logger.info("V2 Root endpoint accessed")
    return {
        "message": "Auto Agents API V2",
        "version": "2.0.0",
        "features": [
            "Enhanced error handling",
            "Improved performance",
            "New authentication system"
        ]
    }
