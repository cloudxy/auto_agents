"""任务模板子域端点：模板 CRUD / 模板一键运行（C1：收藏常用任务配置）

API 层只做参数校验与 Service 编排，不碰 ORM/Session；
响应契约：统一 ApiResponse 信封（ADR-001），载荷置于 data。
"""
from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, require_login, require_operator
from backend.app.api.v1.spiders.deps import _registry_service
from backend.app.responses import ApiResponse, created, deleted, ok, updated
from backend.services.spider_registry_service import SpiderRegistryService
from platform_core.db import get_async_db
from platform_core.schemas.spider import (
    SpiderTaskResponse,
    TaskTemplateRequest,
    TaskTemplateResponse,
    TaskTemplateUpdateRequest,
)

router = APIRouter()


@router.get("/templates", response_model=ApiResponse[list[TaskTemplateResponse]])
async def list_templates(
    service: SpiderRegistryService = Depends(_registry_service),
    _user: CurrentUser = Depends(require_login),
) -> ApiResponse[list[TaskTemplateResponse]]:
    """获取所有任务模板"""
    return ok(await service.list_templates())


@router.post("/templates", response_model=ApiResponse[TaskTemplateResponse])
async def create_template(
    payload: TaskTemplateRequest,
    service: SpiderRegistryService = Depends(_registry_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_operator),
) -> ApiResponse[TaskTemplateResponse]:
    """创建任务模板（收藏当前任务配置）"""
    template = await service.create_template(
        payload.model_dump(), created_by=user.id
    )
    await record_audit(session, user, "template.create", f"template#{template.id}",
                 {"name": payload.name, "spider": payload.spider_name})
    return created(template)


@router.patch("/templates/{template_id}", response_model=ApiResponse[TaskTemplateResponse])
async def update_template(
    payload: TaskTemplateUpdateRequest,
    template_id: int = Path(..., ge=1),
    service: SpiderRegistryService = Depends(_registry_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_operator),
) -> ApiResponse[TaskTemplateResponse]:
    """更新任务模板"""
    template = await service.update_template(
        template_id, payload.model_dump(exclude_unset=True)
    )
    await record_audit(session, user, "template.update", f"template#{template_id}")
    return updated(template)


@router.delete("/templates/{template_id}", response_model=ApiResponse[dict])
async def delete_template(
    template_id: int = Path(..., ge=1),
    service: SpiderRegistryService = Depends(_registry_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_operator),
) -> ApiResponse[dict]:
    """删除任务模板"""
    result = await service.delete_template(template_id)
    await record_audit(session, user, "template.delete", f"template#{template_id}")
    return deleted(data=result)


@router.post("/templates/{template_id}/run", response_model=ApiResponse[SpiderTaskResponse])
async def run_from_template(
    template_id: int = Path(..., ge=1),
    service: SpiderRegistryService = Depends(_registry_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_operator),
) -> ApiResponse[SpiderTaskResponse]:
    """从模板创建并运行任务"""
    task = await service.create_task_from_template(template_id)
    await record_audit(session, user, "task.run_from_template", f"task#{task.id}",
                 {"template_id": template_id})
    return created(task)
