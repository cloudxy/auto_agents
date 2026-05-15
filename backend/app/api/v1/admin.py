"""管理后台相关接口 —— 只做编排，统计数据通过 SpiderService"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.responses import ok
from backend.services.spider_service import SpiderService
from platform_core.db import get_async_db

router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> SpiderService:
    return SpiderService(session)


@router.get("/stats")
async def get_stats(service: SpiderService = Depends(_service)):
    """获取系统统计数据"""
    spider_stats = await service.stats()
    return ok(data={
        "total_tasks": spider_stats.total_tasks,
        "by_status": {
            "pending": spider_stats.pending,
            "running": spider_stats.running,
            "completed": spider_stats.completed,
            "failed": spider_stats.failed,
        },
        "active_nodes": 1,
    })
