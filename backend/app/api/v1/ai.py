"""AI 智能采集接口（阶段二）—— API 层只做参数校验与 Service 编排，不碰 ORM/Session

规划 / 试采为后台异步执行（服务内 asyncio.create_task，自开独立 session），
端点立即返回计划快照；进度通过状态机查询（draft/planning/testing/registered/failed）。
响应契约：统一 ApiResponse 信封（ADR-001）；plans 列表为 PaginatedResponse 分页信封。
"""
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, require_admin, require_login, require_operator
from backend.app.responses import (
    ApiResponse,
    PaginatedResponse,
    created,
    deleted,
    ok,
    paginated_from_offset,
)
from backend.services.ai_planner_service import AiPlannerService
from platform_core.db import get_async_db
from platform_core.schemas.ai_plan import (
    AiPlanCreate,
    AiPlanResponse,
)

router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> AiPlannerService:
    return AiPlannerService(session)


@router.post("/plans", response_model=ApiResponse[AiPlanResponse])
async def create_plan(
    payload: AiPlanCreate,
    service: AiPlannerService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_operator),
) -> ApiResponse[AiPlanResponse]:
    """创建 AI 采集计划（draft，target_url 必填；html_snippet 可选降级离线规划）"""
    plan = await service.create_plan(payload, created_by=user.username)
    await record_audit(session, user, "ai.plan.create", f"ai_plan#{plan.id}",
                 {"target_url": payload.target_url})
    return created(plan)


@router.get("/plans", response_model=PaginatedResponse[AiPlanResponse])
async def list_plans(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None,
                                  description="按状态过滤：draft/planning/testing/registered/failed"),
    service: AiPlannerService = Depends(_service),
    _user: CurrentUser = Depends(require_login),
) -> PaginatedResponse[AiPlanResponse]:
    """AI 采集计划分页列表（支持状态过滤）"""
    resp = await service.list_plans(skip=skip, limit=limit, status=status)
    return paginated_from_offset(items=resp.items, total=resp.total, skip=skip, limit=limit)


@router.get("/plans/{plan_id}", response_model=ApiResponse[AiPlanResponse])
async def get_plan(
    plan_id: int = Path(..., ge=1),
    service: AiPlannerService = Depends(_service),
    _user: CurrentUser = Depends(require_login),
) -> ApiResponse[AiPlanResponse]:
    """AI 采集计划快照（状态机进度查询）"""
    return ok(await service.get_plan(plan_id))


@router.post("/plans/{plan_id}/plan", response_model=ApiResponse[AiPlanResponse])
async def trigger_plan(
    plan_id: int = Path(..., ge=1),
    service: AiPlannerService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_operator),
) -> ApiResponse[AiPlanResponse]:
    """触发 LLM 规划（后台执行，立即返回 planning 快照）"""
    plan = await service.launch_plan(plan_id)
    await record_audit(session, user, "ai.plan.trigger", f"ai_plan#{plan_id}", {"action": "plan"})
    return ok(plan)


@router.post("/plans/{plan_id}/test", response_model=ApiResponse[AiPlanResponse])
async def trigger_test(
    plan_id: int = Path(..., ge=1),
    service: AiPlannerService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_operator),
) -> ApiResponse[AiPlanResponse]:
    """触发 flow_generic 试采（后台执行含自动修复迭代，立即返回快照）"""
    plan = await service.launch_test(plan_id)
    await record_audit(session, user, "ai.plan.trigger", f"ai_plan#{plan_id}", {"action": "test"})
    return ok(plan)


@router.post("/plans/{plan_id}/register", response_model=ApiResponse[AiPlanResponse])
async def register_plan(
    plan_id: int = Path(..., ge=1),
    service: AiPlannerService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[AiPlanResponse]:
    """注册为爬虫定义（M3：内部调 create_definition 与手动登记同级，须 admin；
    校验最近试采通过；source=ai_generated，type=flow）"""
    plan = await service.register(plan_id)
    await record_audit(session, user, "ai.plan.register", f"ai_plan#{plan_id}",
                 {"definition": plan.plan_json.get("registered_definition") if plan.plan_json else None})
    return ok(plan)


@router.delete("/plans/{plan_id}", response_model=ApiResponse[dict])
async def delete_plan(
    plan_id: int = Path(..., ge=1),
    service: AiPlannerService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[dict]:
    """删除 AI 采集计划（仅管理员）"""
    result = await service.delete_plan(plan_id)
    await record_audit(session, user, "ai.plan.delete", f"ai_plan#{plan_id}")
    return deleted(data=result)
