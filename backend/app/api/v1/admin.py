"""管理后台相关接口 - 统计数据等"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from platform_core.db import get_async_db
from platform_core.models.spider_task import SpiderTask
from backend.app.responses import ok

router = APIRouter()

@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_async_db)):
    """获取系统统计数据"""
    # 获取总任务数
    result = await db.execute(select(func.count(SpiderTask.id)))
    task_count = result.scalar()
    
    return ok(data={
        "total_tasks": task_count,
        "active_nodes": 1,  # 示例数据
        "total_data": 12800  # 示例数据
    })
