"""定时调度与告警规则子域端点：调度计划 CRUD / 告警规则 CRUD

API 层只做参数校验与 Service 编排，不碰 ORM/Session；
响应契约：统一 ApiResponse 信封（ADR-001），载荷置于 data。

兼容性说明：告警端点经由包命名空间（_pkg，见文件末尾）查找 AlertService /
record_audit，使存量测试的 patch 路径 backend.app.api.v1.spiders.AlertService /
.record_audit 在拆包后继续生效；调度端点无 patch 需求，record_audit 保持直接导入。
"""
from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, require_admin, require_login, require_operator
from backend.app.api.v1.spiders.deps import _schedule_service
from backend.app.responses import ApiResponse, created, deleted, ok, updated
from backend.services.schedule_service import ScheduleService
from platform_core.db import get_async_db
from platform_core.schemas.spider import (
    AlertRuleRequest,
    AlertRuleResponse,
    AlertRuleUpdateRequest,
    ScheduleRequest,
    ScheduleUpdateRequest,
    SpiderScheduleListResponse,
    SpiderScheduleResponse,
)

router = APIRouter()


# ----------------------------------------------------------------------
# 定时调度（对标 Crawlab 定时任务）
# ----------------------------------------------------------------------
@router.get("/schedules", response_model=ApiResponse[SpiderScheduleListResponse])
async def list_schedules(
    service: ScheduleService = Depends(_schedule_service),
    _user: CurrentUser = Depends(require_login),
) -> ApiResponse[SpiderScheduleListResponse]:
    """调度计划列表"""
    return ok(await service.list_schedules())


@router.post("/schedules", response_model=ApiResponse[SpiderScheduleResponse])
async def create_schedule(
    payload: ScheduleRequest,
    service: ScheduleService = Depends(_schedule_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[SpiderScheduleResponse]:
    """创建调度计划（校验爬虫注册表 / cron 合法性 / 同爬虫唯一；仅管理员）"""
    schedule = await service.create_schedule(payload)
    await record_audit(session, user, "schedule.create", payload.spider_name,
                 {"cron": payload.cron_expr, "enabled": payload.enabled})
    return created(schedule)


@router.patch("/schedules/{schedule_id}", response_model=ApiResponse[SpiderScheduleResponse])
async def update_schedule(
    payload: ScheduleUpdateRequest,
    schedule_id: int = Path(..., ge=1),
    service: ScheduleService = Depends(_schedule_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[SpiderScheduleResponse]:
    """更新调度计划（启停 / 改表达式 / 改参数；仅管理员）"""
    schedule = await service.update_schedule(schedule_id, payload)
    await record_audit(session, user, "schedule.update", f"schedule#{schedule_id}",
                 payload.model_dump(exclude_unset=True))
    return updated(schedule)


@router.delete("/schedules/{schedule_id}", response_model=ApiResponse[dict])
async def delete_schedule(
    schedule_id: int = Path(..., ge=1),
    service: ScheduleService = Depends(_schedule_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[dict]:
    """删除调度计划（仅管理员）"""
    result = await service.delete_schedule(schedule_id)
    await record_audit(session, user, "schedule.delete", f"schedule#{schedule_id}")
    return deleted(data=result)


# ----------------------------------------------------------------------
# 告警规则管理（B2）—— AlertService / record_audit 经包命名空间 _pkg 查找
# ----------------------------------------------------------------------
@router.get("/alert-rules", response_model=ApiResponse[list[dict]])
async def list_alert_rules(
    session: AsyncSession = Depends(get_async_db),
    _user: CurrentUser = Depends(require_operator),
) -> ApiResponse[list[dict]]:
    """获取告警规则列表"""
    svc = _pkg.AlertService(session)
    return ok(await svc.list_rules())


@router.post("/alert-rules", response_model=ApiResponse[AlertRuleResponse])
async def create_alert_rule(
    body: AlertRuleRequest,
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[AlertRuleResponse]:
    """创建告警规则（仅管理员）"""
    svc = _pkg.AlertService(session)
    result = await svc.create_rule(body.model_dump())
    await _pkg.record_audit(session, user, "alert_rule.create", f"alert_rule#{result['id']}",
                 {"name": body.name, "rule_type": body.rule_type, "spider": body.spider_name})
    return created(AlertRuleResponse(**result))


@router.patch("/alert-rules/{rule_id}", response_model=ApiResponse[AlertRuleResponse])
async def update_alert_rule(
    rule_id: int = Path(..., ge=1),
    body: AlertRuleUpdateRequest = ...,
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[AlertRuleResponse]:
    """更新告警规则（仅管理员）"""
    svc = _pkg.AlertService(session)
    result = await svc.update_rule(rule_id, body.model_dump(exclude_unset=True))
    await _pkg.record_audit(session, user, "alert_rule.update", f"alert_rule#{rule_id}",
                 body.model_dump(exclude_unset=True))
    return updated(AlertRuleResponse(**result))


@router.delete("/alert-rules/{rule_id}", response_model=ApiResponse[dict])
async def delete_alert_rule(
    rule_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[dict]:
    """删除告警规则（仅管理员）"""
    svc = _pkg.AlertService(session)
    result = await svc.delete_rule(rule_id)
    await _pkg.record_audit(session, user, "alert_rule.delete", f"alert_rule#{rule_id}")
    return deleted(data=result)


# 包命名空间向后兼容：告警端点在调用时经 _pkg 查找 AlertService / record_audit，
# 使旧 patch 路径 backend.app.api.v1.spiders.AlertService / .record_audit 在拆包后
# 继续生效。文件末行 import：包与子模块双向初始化安全（sys.modules 部分绑定）。
import backend.app.api.v1.spiders as _pkg  # noqa: E402
