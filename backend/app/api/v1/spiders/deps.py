"""spiders 路由包共享依赖工厂（FastAPI Depends，不承载端点）

期 4 Facade 退役：原 SpiderService 门面按子域拆为三个独立 Service，
端点按职责注入对应子 Service（任务/结果/注册表）。
"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.schedule_service import ScheduleService
from backend.services.spider_query_service import SpiderQueryService
from backend.services.spider_registry_service import SpiderRegistryService
from backend.services.spider_task_service import SpiderTaskService
from platform_core.db import get_async_db


def _task_service(session: AsyncSession = Depends(get_async_db)) -> SpiderTaskService:
    return SpiderTaskService(session)


def _query_service(session: AsyncSession = Depends(get_async_db)) -> SpiderQueryService:
    return SpiderQueryService(session)


def _registry_service(session: AsyncSession = Depends(get_async_db)) -> SpiderRegistryService:
    return SpiderRegistryService(session)


def _schedule_service(session: AsyncSession = Depends(get_async_db)) -> ScheduleService:
    return ScheduleService(session)
