"""爬虫任务相关接口 —— API 层只做参数校验与 Service 编排，不碰 ORM/Session"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.spider_service import SpiderService
from platform_core.db import get_async_db
from platform_core.schemas.spider import (
    RunSpiderRequest,
    SpiderTaskListResponse,
    SpiderTaskResponse,
)

router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> SpiderService:
    return SpiderService(session)


@router.get("/tasks", response_model=SpiderTaskListResponse)
async def list_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="pending/running/completed/failed"),
    service: SpiderService = Depends(_service),
) -> SpiderTaskListResponse:
    """获取爬虫任务列表（支持分页和筛选）"""
    return await service.list_tasks(skip=skip, limit=limit, status=status)


@router.post("/run", response_model=SpiderTaskResponse)
async def run_spider(
    payload: RunSpiderRequest,
    service: SpiderService = Depends(_service),
) -> SpiderTaskResponse:
    """入队一次爬虫任务"""
    return await service.enqueue(spider_name=payload.spider_name, params=payload.params)
