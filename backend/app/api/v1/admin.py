"""后台管理接口"""
from fastapi import APIRouter

router = APIRouter()

@router.get("/stats")
async def get_stats():
    """获取系统统计信息"""
    return {"users": 0, "tasks": 0, "spiders": 0}
