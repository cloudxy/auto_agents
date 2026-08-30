"""爬虫任务接口 —— API 层只做参数校验与 Service 编排，不碰 ORM/Session

响应格式：直接返回 domain-specific Pydantic 模型（SpiderTaskResponse 等），
不使用 ApiResponse 包装（与 auth/admin 模块的 ok() 包装不同）。
"""
from typing import Optional

from datetime import datetime

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, require_admin, require_login, require_operator
from backend.services.alert_service import AlertService
from backend.services.schedule_service import ScheduleService
from backend.services.spider_service import SpiderService
from platform_core.db import get_async_db
from platform_core.schemas.spider import (
    AlertRuleRequest,
    AlertRuleResponse,
    AlertRuleUpdateRequest,
    DefinitionCreateRequest,
    DefinitionUpdateMetaRequest,
    DefinitionUpdateRequest,
    RunSpiderRequest,
    ScheduleRequest,
    ScheduleUpdateRequest,
    SpiderDefinitionResponse,
    SpiderFileListResponse,
    SpiderRegistryResponse,
    SpiderResultListResponse,
    SpiderScheduleListResponse,
    SpiderScheduleResponse,
    SpiderTaskListResponse,
    SpiderTaskResponse,
    TaskControlRequest,
    TaskLogResponse,
    TaskQualityReportResponse,
    TaskStoreStatusResponse,
    TaskTemplateRequest,
    TaskTemplateResponse,
    TaskTemplateUpdateRequest,
    TaskUpdateRequest,
    WorkerNodeListResponse,
)

router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> SpiderService:
    return SpiderService(session)


def _schedule_service(session: AsyncSession = Depends(get_async_db)) -> ScheduleService:
    return ScheduleService(session)


@router.get("/tasks", response_model=SpiderTaskListResponse)
async def list_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="pending/running/completed/failed"),
    priority: Optional[str] = Query(None, pattern="^(high|normal|low)$", description="按优先级过滤"),
    service: SpiderService = Depends(_service),
    _user: CurrentUser = Depends(require_login),
) -> SpiderTaskListResponse:
    """获取爬虫任务列表（支持分页和状态/优先级筛选）"""
    return await service.list_tasks(skip=skip, limit=limit, status=status, priority=priority)


@router.post("/run", response_model=SpiderTaskResponse)
async def run_spider(
    payload: RunSpiderRequest,
    service: SpiderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_operator),
) -> SpiderTaskResponse:
    """入队一次爬虫任务（params 为 JSON 字符串，如 '{"urls": ["https://..."]}'；可指定优先级）"""
    task = await service.enqueue(
        spider_name=payload.spider_name, params=payload.params, priority=payload.priority
    )
    await record_audit(session, user, "task.run", f"task#{task.id}",
                 {"spider": payload.spider_name, "priority": payload.priority})
    return task


@router.get("/results", response_model=SpiderResultListResponse)
async def search_results(
    spider_name: Optional[str] = Query(None, max_length=100, description="按爬虫名过滤（不传查全部）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start_time: Optional[datetime] = Query(None, description="采集时间起（ISO 8601）"),
    end_time: Optional[datetime] = Query(None, description="采集时间止（ISO 8601）"),
    keyword: Optional[str] = Query(None, max_length=100, description="关键词（匹配标题/URL/内容）"),
    service: SpiderService = Depends(_service),
    _user: CurrentUser = Depends(require_login),
) -> SpiderResultListResponse:
    """跨任务分页查询采集结果（数据中心：爬虫/时间范围/关键词过滤）"""
    return await service.search_results(
        spider_name=spider_name,
        page=page,
        page_size=page_size,
        start_time=start_time,
        end_time=end_time,
        keyword=keyword,
    )


@router.delete("/results/{result_id}")
async def delete_result(
    result_id: int = Path(..., ge=1),
    service: SpiderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> dict:
    """删除单条采集结果（数据中心清理；仅管理员）"""
    result = await service.delete_result(result_id)
    await record_audit(session, user, "result.delete", f"result#{result_id}")
    return result


@router.get("/results/{task_id}", response_model=SpiderResultListResponse)
async def list_results(
    task_id: int = Path(..., ge=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    service: SpiderService = Depends(_service),
    _user: CurrentUser = Depends(require_login),
) -> SpiderResultListResponse:
    """查询指定任务的采集结果（数据闭环出口）"""
    return await service.list_results(task_id=task_id, skip=skip, limit=limit)


@router.get("/results/{task_id}/export")
async def export_results(
    task_id: int = Path(..., ge=1),
    format: str = Query("csv", pattern="^(csv|json)$", description="导出格式：csv/json"),
    service: SpiderService = Depends(_service),
    _user: CurrentUser = Depends(require_login),
) -> Response:
    """导出指定任务的全部采集结果（下载附件）"""
    content, filename, media_type = await service.export_results(task_id, format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/tasks/{task_id}/store", response_model=TaskStoreStatusResponse)
async def task_store_status(
    task_id: int = Path(..., ge=1),
    service: SpiderService = Depends(_service),
    _user: CurrentUser = Depends(require_login),
) -> TaskStoreStatusResponse:
    """任务的额外存储目标状态（4.2：目标清单 / redis 缓存条数 / csv 落盘路径）"""
    return await service.store_status(task_id)


@router.get("/registry", response_model=SpiderRegistryResponse)
async def get_registry(
    service: SpiderService = Depends(_service),
    _user: CurrentUser = Depends(require_login),
) -> SpiderRegistryResponse:
    """爬虫注册表：类型表单定义 + 可调度爬虫清单（新增任务弹窗的数据源；清单 DB 优先）"""
    return await service.registry()


@router.get("/nodes", response_model=WorkerNodeListResponse)
async def list_nodes(
    service: SpiderService = Depends(_service),
    _user: CurrentUser = Depends(require_login),
) -> WorkerNodeListResponse:
    """Worker 节点列表（心跳在线状态 + 各爬虫活跃任务，数据源为 Redis 心跳键）"""
    return await service.list_nodes()


@router.get("/files", response_model=SpiderFileListResponse)
async def list_spider_files(
    service: SpiderService = Depends(_service),
    _user: CurrentUser = Depends(require_login),
) -> SpiderFileListResponse:
    """代码爬虫文件清单（4.4：只读文件元数据 + 关联启停状态）"""
    return await service.spider_files()


@router.patch("/definitions/{name}", response_model=SpiderDefinitionResponse)
async def update_definition(
    payload: DefinitionUpdateRequest,
    name: str = Path(..., min_length=1, max_length=50),
    service: SpiderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> SpiderDefinitionResponse:
    """启停代码爬虫（4.4：写 spider_definitions.enabled，仅 admin）"""
    definition = await service.update_definition(name, payload.enabled)
    await record_audit(session, user, "definition.update", f"definition#{name}",
                 {"enabled": payload.enabled})
    return definition


@router.post("/definitions", response_model=SpiderDefinitionResponse)
async def create_definition(
    payload: DefinitionCreateRequest,
    service: SpiderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> SpiderDefinitionResponse:
    """新建爬虫定义（手动登记，来源标记 manual；仅管理员）"""
    definition = await service.create_definition(payload)
    await record_audit(session, user, "definition.create", f"definition#{payload.name}",
                 {"type": payload.type, "source": "manual"})
    return definition


@router.patch("/definitions/{name}/meta", response_model=SpiderDefinitionResponse)
async def update_definition_meta(
    payload: DefinitionUpdateMetaRequest,
    name: str = Path(..., min_length=1, max_length=50),
    service: SpiderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> SpiderDefinitionResponse:
    """编辑爬虫定义元信息（标题/描述；仅管理员）"""
    definition = await service.update_definition_meta(name, payload)
    await record_audit(session, user, "definition.update_meta", f"definition#{name}",
                 payload.model_dump(exclude_unset=True))
    return definition


@router.delete("/definitions/{name}")
async def delete_definition(
    name: str = Path(..., min_length=1, max_length=50),
    service: SpiderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> dict:
    """删除爬虫定义（存在历史任务引用时拒绝；仅管理员）"""
    result = await service.delete_definition(name)
    await record_audit(session, user, "definition.delete", f"definition#{name}")
    return result


@router.patch("/tasks/{task_id}", response_model=SpiderTaskResponse)
async def update_task(
    payload: TaskUpdateRequest,
    task_id: int = Path(..., ge=1),
    service: SpiderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_operator),
) -> SpiderTaskResponse:
    """编辑待执行任务（仅 pending/queued 可改参数/优先级；待执行任务改优先级会同步搬迁队列）"""
    task = await service.update_task(
        task_id, params=payload.params, priority=payload.priority
    )
    await record_audit(session, user, "task.update", f"task#{task_id}",
                 payload.model_dump(exclude_unset=True))
    return task


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: int = Path(..., ge=1),
    service: SpiderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> dict:
    """删除任务及其采集结果（running 状态拒绝删除；仅管理员）"""
    result = await service.delete_task(task_id)
    await record_audit(session, user, "task.delete", f"task#{task_id}")
    return result


@router.post("/tasks/{task_id}/control")
async def control_task(
    payload: TaskControlRequest,
    task_id: int = Path(..., ge=1),
    service: SpiderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_operator),
) -> dict:
    """控制运行中的任务：暂停/恢复/终止（A4；body 必填，缺失时 422）"""
    result = await service.control_task(task_id, payload.action)
    await record_audit(session, user, "task.control", f"task#{task_id}", {"action": payload.action})
    return result


@router.get("/tasks/{task_id}/logs", response_model=TaskLogResponse)
async def get_task_logs(
    task_id: int = Path(..., ge=1),
    lines: int = Query(200, ge=1, le=500),
    keyword: Optional[str] = Query(None, description="全文搜索关键词（大小写不敏感）"),
    level: Optional[str] = Query(None, description="日志级别过滤：DEBUG/INFO/WARNING/ERROR/CRITICAL"),
    service: SpiderService = Depends(_service),
    _user: CurrentUser = Depends(require_login),
) -> TaskLogResponse:
    """任务运行日志（尾部 N 行，支持关键词搜索和级别过滤）"""
    return await service.task_logs(task_id, lines=lines, keyword=keyword, level=level)


@router.get("/tasks/{task_id}/quality", response_model=TaskQualityReportResponse)
async def get_task_quality(
    task_id: int = Path(..., ge=1),
    service: SpiderService = Depends(_service),
    _user: CurrentUser = Depends(require_login),
) -> TaskQualityReportResponse:
    """获取任务数据质量报告（B1：平均/最低/最高分 + 四档分布）"""
    return await service.get_task_quality(task_id)


# ----------------------------------------------------------------------
# 定时调度（对标 Crawlab 定时任务）
# ----------------------------------------------------------------------
@router.get("/schedules", response_model=SpiderScheduleListResponse)
async def list_schedules(
    service: ScheduleService = Depends(_schedule_service),
    _user: CurrentUser = Depends(require_login),
) -> SpiderScheduleListResponse:
    """调度计划列表"""
    return await service.list_schedules()


@router.post("/schedules", response_model=SpiderScheduleResponse)
async def create_schedule(
    payload: ScheduleRequest,
    service: ScheduleService = Depends(_schedule_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> SpiderScheduleResponse:
    """创建调度计划（校验爬虫注册表 / cron 合法性 / 同爬虫唯一；仅管理员）"""
    schedule = await service.create_schedule(payload)
    await record_audit(session, user, "schedule.create", payload.spider_name,
                 {"cron": payload.cron_expr, "enabled": payload.enabled})
    return schedule


@router.patch("/schedules/{schedule_id}", response_model=SpiderScheduleResponse)
async def update_schedule(
    payload: ScheduleUpdateRequest,
    schedule_id: int = Path(..., ge=1),
    service: ScheduleService = Depends(_schedule_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> SpiderScheduleResponse:
    """更新调度计划（启停 / 改表达式 / 改参数；仅管理员）"""
    schedule = await service.update_schedule(schedule_id, payload)
    await record_audit(session, user, "schedule.update", f"schedule#{schedule_id}",
                 payload.model_dump(exclude_unset=True))
    return schedule


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: int = Path(..., ge=1),
    service: ScheduleService = Depends(_schedule_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> dict:
    """删除调度计划（仅管理员）"""
    result = await service.delete_schedule(schedule_id)
    await record_audit(session, user, "schedule.delete", f"schedule#{schedule_id}")
    return result


# ----------------------------------------------------------------------
# 代理池健康管理（B3）
# ----------------------------------------------------------------------
@router.get("/proxy-health")
async def get_proxy_health(
    _user: CurrentUser = Depends(require_operator),
) -> list[dict]:
    """代理评分排行（评分驱动的智能代理管理）"""
    from backend.services.proxy_health_service import ProxyHealthService

    service = ProxyHealthService()
    return await service.get_proxy_health()


# ----------------------------------------------------------------------
# 告警规则管理（B2）
# ----------------------------------------------------------------------
@router.get("/alert-rules")
async def list_alert_rules(
    session: AsyncSession = Depends(get_async_db),
    _user: CurrentUser = Depends(require_operator),
) -> list[dict]:
    """获取告警规则列表"""
    svc = AlertService(session)
    return await svc.list_rules()


@router.post("/alert-rules", response_model=AlertRuleResponse)
async def create_alert_rule(
    body: AlertRuleRequest,
    session: AsyncSession = Depends(get_async_db),
    _user: CurrentUser = Depends(require_admin),
) -> AlertRuleResponse:
    """创建告警规则（仅管理员）"""
    svc = AlertService(session)
    result = await svc.create_rule(body.model_dump())
    return AlertRuleResponse(**result)


@router.patch("/alert-rules/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: int = Path(..., ge=1),
    body: AlertRuleUpdateRequest = ...,
    session: AsyncSession = Depends(get_async_db),
    _user: CurrentUser = Depends(require_admin),
) -> AlertRuleResponse:
    """更新告警规则（仅管理员）"""
    svc = AlertService(session)
    result = await svc.update_rule(rule_id, body.model_dump(exclude_unset=True))
    return AlertRuleResponse(**result)


@router.delete("/alert-rules/{rule_id}")
async def delete_alert_rule(
    rule_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(get_async_db),
    _user: CurrentUser = Depends(require_admin),
) -> dict:
    """删除告警规则（仅管理员）"""
    svc = AlertService(session)
    return await svc.delete_rule(rule_id)


# ----------------------------------------------------------------------
# 任务模板（C1）：收藏常用任务配置，一键创建任务
# ----------------------------------------------------------------------
@router.get("/templates", response_model=list[TaskTemplateResponse])
async def list_templates(
    service: SpiderService = Depends(_service),
    _user: CurrentUser = Depends(require_login),
) -> list[TaskTemplateResponse]:
    """获取所有任务模板"""
    return await service.list_templates()


@router.post("/templates", response_model=TaskTemplateResponse)
async def create_template(
    payload: TaskTemplateRequest,
    service: SpiderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_operator),
) -> TaskTemplateResponse:
    """创建任务模板（收藏当前任务配置）"""
    template = await service.create_template(
        payload.model_dump(), created_by=user.id
    )
    await record_audit(session, user, "template.create", f"template#{template.id}",
                 {"name": payload.name, "spider": payload.spider_name})
    return template


@router.patch("/templates/{template_id}", response_model=TaskTemplateResponse)
async def update_template(
    payload: TaskTemplateUpdateRequest,
    template_id: int = Path(..., ge=1),
    service: SpiderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_operator),
) -> TaskTemplateResponse:
    """更新任务模板"""
    template = await service.update_template(
        template_id, payload.model_dump(exclude_unset=True)
    )
    await record_audit(session, user, "template.update", f"template#{template_id}")
    return template


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int = Path(..., ge=1),
    service: SpiderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_operator),
) -> dict:
    """删除任务模板"""
    result = await service.delete_template(template_id)
    await record_audit(session, user, "template.delete", f"template#{template_id}")
    return result


@router.post("/templates/{template_id}/run", response_model=SpiderTaskResponse)
async def run_from_template(
    template_id: int = Path(..., ge=1),
    service: SpiderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_operator),
) -> SpiderTaskResponse:
    """从模板创建并运行任务"""
    task = await service.create_task_from_template(template_id)
    await record_audit(session, user, "task.run_from_template", f"task#{task.id}",
                 {"template_id": template_id})
    return task
