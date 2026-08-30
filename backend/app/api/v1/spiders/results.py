"""采集结果子域端点：跨任务查询 / 按任务查询 / 删除 / 导出

响应契约：统一 ApiResponse / PaginatedResponse 信封（ADR-001）；
例外：GET /results/{task_id}/export 为二进制流下载（白名单，StreamingResponse 分批下发）。
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, require_admin, require_login
from backend.app.api.v1.spiders.deps import _query_service
from backend.app.responses import (
    ApiResponse,
    PaginatedResponse,
    deleted,
    paginated,
    paginated_from_offset,
)
from backend.services.spider_query_service import SpiderQueryService
from platform_core.db import get_async_db
from platform_core.schemas.spider import SpiderResultResponse

router = APIRouter()


@router.get("/results", response_model=PaginatedResponse[SpiderResultResponse])
async def search_results(
    spider_name: Optional[str] = Query(None, max_length=100, description="按爬虫名过滤（不传查全部）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start_time: Optional[datetime] = Query(None, description="采集时间起（ISO 8601）"),
    end_time: Optional[datetime] = Query(None, description="采集时间止（ISO 8601）"),
    keyword: Optional[str] = Query(None, max_length=100, description="关键词（匹配标题/URL/内容）"),
    service: SpiderQueryService = Depends(_query_service),
    _user: CurrentUser = Depends(require_login),
) -> PaginatedResponse[SpiderResultResponse]:
    """跨任务分页查询采集结果（数据中心：爬虫/时间范围/关键词过滤）"""
    resp = await service.search_results(
        spider_name=spider_name,
        page=page,
        page_size=page_size,
        start_time=start_time,
        end_time=end_time,
        keyword=keyword,
    )
    return paginated(
        items=resp.items, total=resp.total, page=page, page_size=page_size
    )


@router.delete("/results/{result_id}", response_model=ApiResponse[dict])
async def delete_result(
    result_id: int = Path(..., ge=1),
    service: SpiderQueryService = Depends(_query_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[dict]:
    """删除单条采集结果（数据中心清理；仅管理员）"""
    result = await service.delete_result(result_id)
    await record_audit(session, user, "result.delete", f"result#{result_id}")
    return deleted(data=result)


@router.get("/results/{task_id}", response_model=PaginatedResponse[SpiderResultResponse])
async def list_results(
    task_id: int = Path(..., ge=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    service: SpiderQueryService = Depends(_query_service),
    _user: CurrentUser = Depends(require_login),
) -> PaginatedResponse[SpiderResultResponse]:
    """查询指定任务的采集结果（数据闭环出口）"""
    resp = await service.list_results(task_id=task_id, skip=skip, limit=limit)
    return paginated_from_offset(items=resp.items, total=resp.total, skip=skip, limit=limit)


@router.get("/results/{task_id}/export")
async def export_results(
    task_id: int = Path(..., ge=1),
    format: str = Query("csv", pattern="^(csv|json)$", description="导出格式：csv/json"),
    service: SpiderQueryService = Depends(_query_service),
    _user: CurrentUser = Depends(require_login),
) -> StreamingResponse:
    """导出指定任务的全部采集结果（下载附件，流式传输避免大任务内存峰值）"""
    stream, filename, media_type = await service.export_results(task_id, format)
    return StreamingResponse(
        stream,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
