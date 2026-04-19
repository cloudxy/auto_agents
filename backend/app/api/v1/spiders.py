"""爬虫相关接口"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from platform_core.models.spider_task import SpiderTask as SpiderTaskModel
from platform_core.db import get_async_db
from platform_core.repository import BaseRepository

router = APIRouter()

@router.get("/tasks")
async def list_tasks(
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    session: AsyncSession = Depends(get_async_db)
):
    """获取爬虫任务列表（支持分页和筛选）"""
    repo = BaseRepository(SpiderTaskModel, session)
    # 简单实现：实际生产中应在 Repo 中增加 filter_by 逻辑
    tasks = await repo.get_all(skip=skip, limit=limit)
    return {"total": len(tasks), "items": tasks}

@router.post("/run")
async def run_spider(spider_name: str, session: AsyncSession = Depends(get_async_db)):
    """运行爬虫任务"""
    task = SpiderTaskModel(spider_name=spider_name, status="pending")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return {"message": f"Spider {spider_name} started", "task_id": task.id}
