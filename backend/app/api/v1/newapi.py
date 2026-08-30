"""new-api 中转站管控接口（阶段三）—— 全只读：渠道总览 / 事件 / 探针结果

设计：
- 无写代理（渠道启停仍由调度器/人工在 new-api 侧操作），三端点全部 GET
- overview 聚合远程渠道列表与本地统计；远程异常/超时/开关关闭时 HTTP 200 降级
  available=false（不 500）；events / probe-results 直出本地表，始终可用
- 响应格式与 ai.py / llm_providers.py 一致：Pydantic 模型直出（无信封）
- 全部 require_admin（中转站管控仅管理员可见，与前端 menu:newapi 权限对齐）
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import CurrentUser, require_admin
from backend.services.newapi_overview_service import NewapiOverviewService
from platform_core.db import get_async_db
from platform_core.schemas.newapi import (
    ChannelEventListResponse,
    ChannelProbeResultListResponse,
    NewapiOverviewResponse,
)

router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> NewapiOverviewService:
    return NewapiOverviewService(session)


@router.get("/overview", response_model=NewapiOverviewResponse)
async def get_overview(
    service: NewapiOverviewService = Depends(_service),
    _user: CurrentUser = Depends(require_admin),
) -> NewapiOverviewResponse:
    """中转站总览：远程渠道列表（异常降级 available=false）+ 本地事件/探针统计"""
    return await service.get_overview()


@router.get("/events", response_model=ChannelEventListResponse)
async def list_events(
    channel_id: Optional[int] = Query(None, description="按 new-api 渠道 ID 过滤"),
    page: int = Query(1, ge=1, description="页码（1 起）"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    service: NewapiOverviewService = Depends(_service),
    _user: CurrentUser = Depends(require_admin),
) -> ChannelEventListResponse:
    """渠道启停事件分页（时间倒序；本地表，始终可用）"""
    return await service.list_events(channel_id=channel_id, page=page, page_size=page_size)


@router.get("/probe-results", response_model=ChannelProbeResultListResponse)
async def list_probe_results(
    channel_id: Optional[int] = Query(None, description="按 new-api 渠道 ID 过滤"),
    page: int = Query(1, ge=1, description="页码（1 起）"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    service: NewapiOverviewService = Depends(_service),
    _user: CurrentUser = Depends(require_admin),
) -> ChannelProbeResultListResponse:
    """渠道真伪探针结果分页（时间倒序；本地表，始终可用）"""
    return await service.list_probe_results(
        channel_id=channel_id, page=page, page_size=page_size
    )
