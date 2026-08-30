"""爬虫任务子域端点：任务列表 / 入队 / 编辑 / 删除 / 控制 / 日志 / 质量 / 存储状态

API 层只做参数校验与 Service 编排，不碰 ORM/Session；
响应契约：统一 ApiResponse / PaginatedResponse 信封（ADR-001），载荷置于 data。
"""
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, require_admin, require_login, require_operator
from backend.app.api.v1.spiders.deps import _query_service, _task_service
from backend.app.responses import (
    ApiResponse,
    PaginatedResponse,
    created,
    deleted,
    ok,
    paginated_from_offset,
    updated,
)
from backend.services.spider_query_service import SpiderQueryService
from backend.services.spider_task_service import SpiderTaskService
from platform_core.db import get_async_db
from platform_core.schemas.spider import (
    SpiderTaskResponse,
    TaskControlRequest,
    TaskLogResponse,
    TaskQualityReportResponse,
    TaskStoreStatusResponse,
    TaskUpdateRequest,
    RunSpiderRequest,
)

router = APIRouter()


@router.get("/tasks", response_model=PaginatedResponse[SpiderTaskResponse])
async def list_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="pending/running/completed/failed"),
    priority: Optional[str] = Query(None, pattern="^(high|normal|low)$", description="按优先级过滤"),
    service: SpiderTaskService = Depends(_task_service),
    _user: CurrentUser = Depends(require_login),
) -> PaginatedResponse[SpiderTaskResponse]:
    """获取爬虫任务列表（支持分页和状态/优先级筛选）"""
    resp = await service.list_tasks(skip=skip, limit=limit, status=status, priority=priority)
    return paginated_from_offset(items=resp.items, total=resp.total, skip=skip, limit=limit)


@router.post("/run", response_model=ApiResponse[SpiderTaskResponse])
async def run_spider(
    payload: RunSpiderRequest,
    service: SpiderTaskService = Depends(_task_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_operator),
) -> ApiResponse[SpiderTaskResponse]:
    """入队一次爬虫任务（params 为 JSON 字符串，如 '{"urls": ["https://..."]}'；可指定优先级）"""
    task = await service.enqueue(
        spider_name=payload.spider_name, params=payload.params, priority=payload.priority
    )
    await record_audit(session, user, "task.run", f"task#{task.id}",
                 {"spider": payload.spider_name, "priority": payload.priority})
    return created(task)


@router.get("/tasks/{task_id}/store", response_model=ApiResponse[TaskStoreStatusResponse])
async def task_store_status(
    task_id: int = Path(..., ge=1),
    service: SpiderQueryService = Depends(_query_service),
    _user: CurrentUser = Depends(require_login),
) -> ApiResponse[TaskStoreStatusResponse]:
    """任务的额外存储目标状态（4.2：目标清单 / redis 缓存条数 / csv 落盘路径）"""
    return ok(await service.store_status(task_id))


@router.patch("/tasks/{task_id}", response_model=ApiResponse[SpiderTaskResponse])
async def update_task(
    payload: TaskUpdateRequest,
    task_id: int = Path(..., ge=1),
    service: SpiderTaskService = Depends(_task_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_operator),
) -> ApiResponse[SpiderTaskResponse]:
    """编辑待执行任务（仅 pending/queued 可改参数/优先级；待执行任务改优先级会同步搬迁队列）"""
    task = await service.update_task(
        task_id, params=payload.params, priority=payload.priority
    )
    await record_audit(session, user, "task.update", f"task#{task_id}",
                 payload.model_dump(exclude_unset=True))
    return updated(task)


@router.delete("/tasks/{task_id}", response_model=ApiResponse[dict])
async def delete_task(
    task_id: int = Path(..., ge=1),
    service: SpiderTaskService = Depends(_task_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[dict]:
    """删除任务及其采集结果（running 状态拒绝删除；仅管理员）"""
    result = await service.delete_task(task_id)
    await record_audit(session, user, "task.delete", f"task#{task_id}")
    return deleted(data=result)


@router.post("/tasks/{task_id}/control", response_model=ApiResponse[dict])
async def control_task(
    payload: TaskControlRequest,
    task_id: int = Path(..., ge=1),
    service: SpiderTaskService = Depends(_task_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_operator),
) -> ApiResponse[dict]:
    """控制运行中的任务：暂停/恢复/终止（A4；body 必填，缺失时 422）"""
    result = await service.control_task(task_id, payload.action)
    await record_audit(session, user, "task.control", f"task#{task_id}", {"action": payload.action})
    return ok(result)


@router.get("/tasks/{task_id}/logs", response_model=ApiResponse[TaskLogResponse])
async def get_task_logs(
    task_id: int = Path(..., ge=1),
    lines: int = Query(200, ge=1, le=500),
    keyword: Optional[str] = Query(None, description="全文搜索关键词（大小写不敏感）"),
    level: Optional[str] = Query(None, description="日志级别过滤：DEBUG/INFO/WARNING/ERROR/CRITICAL"),
    service: SpiderQueryService = Depends(_query_service),
    _user: CurrentUser = Depends(require_login),
) -> ApiResponse[TaskLogResponse]:
    """任务运行日志（尾部 N 行，支持关键词搜索和级别过滤）"""
    return ok(await service.task_logs(task_id, lines=lines, keyword=keyword, level=level))


@router.get("/tasks/{task_id}/quality", response_model=ApiResponse[TaskQualityReportResponse])
async def get_task_quality(
    task_id: int = Path(..., ge=1),
    service: SpiderQueryService = Depends(_query_service),
    _user: CurrentUser = Depends(require_login),
) -> ApiResponse[TaskQualityReportResponse]:
    """获取任务数据质量报告（B1：平均/最低/最高分 + 四档分布）"""
    return ok(await service.get_task_quality(task_id))
