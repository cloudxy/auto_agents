"""爬虫注册表子域端点：注册表 / Worker 节点 / 文件清单 / 定义 CRUD / 代理健康

API 层只做参数校验与 Service 编排，不碰 ORM/Session；
响应契约：统一 ApiResponse 信封（ADR-001），载荷置于 data。
"""
from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, require_admin, require_login, require_operator
from backend.app.api.v1.spiders.deps import _registry_service
from backend.app.responses import ApiResponse, created, deleted, ok, updated
from backend.services.spider_registry_service import SpiderRegistryService
from platform_core.db import get_async_db
from platform_core.schemas.spider import (
    DefinitionCreateRequest,
    DefinitionUpdateMetaRequest,
    DefinitionUpdateRequest,
    SpiderDefinitionResponse,
    SpiderFileListResponse,
    SpiderRegistryResponse,
    WorkerNodeListResponse,
)

router = APIRouter()


@router.get("/registry", response_model=ApiResponse[SpiderRegistryResponse])
async def get_registry(
    service: SpiderRegistryService = Depends(_registry_service),
    _user: CurrentUser = Depends(require_login),
) -> ApiResponse[SpiderRegistryResponse]:
    """爬虫注册表：类型表单定义 + 可调度爬虫清单（新增任务弹窗的数据源；清单 DB 优先）"""
    return ok(await service.registry())


@router.get("/nodes", response_model=ApiResponse[WorkerNodeListResponse])
async def list_nodes(
    service: SpiderRegistryService = Depends(_registry_service),
    _user: CurrentUser = Depends(require_login),
) -> ApiResponse[WorkerNodeListResponse]:
    """Worker 节点列表（心跳在线状态 + 各爬虫活跃任务，数据源为 Redis 心跳键）"""
    return ok(await service.list_nodes())


@router.get("/files", response_model=ApiResponse[SpiderFileListResponse])
async def list_spider_files(
    service: SpiderRegistryService = Depends(_registry_service),
    _user: CurrentUser = Depends(require_login),
) -> ApiResponse[SpiderFileListResponse]:
    """代码爬虫文件清单（4.4：只读文件元数据 + 关联启停状态）"""
    return ok(await service.spider_files())


@router.patch("/definitions/{name}", response_model=ApiResponse[SpiderDefinitionResponse])
async def update_definition(
    payload: DefinitionUpdateRequest,
    name: str = Path(..., min_length=1, max_length=50),
    service: SpiderRegistryService = Depends(_registry_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[SpiderDefinitionResponse]:
    """启停代码爬虫（4.4：写 spider_definitions.enabled，仅 admin）"""
    definition = await service.update_definition(name, payload.enabled)
    await record_audit(session, user, "definition.update", f"definition#{name}",
                 {"enabled": payload.enabled})
    return updated(definition)


@router.post("/definitions", response_model=ApiResponse[SpiderDefinitionResponse])
async def create_definition(
    payload: DefinitionCreateRequest,
    service: SpiderRegistryService = Depends(_registry_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[SpiderDefinitionResponse]:
    """新建爬虫定义（手动登记，来源标记 manual；仅管理员）"""
    definition = await service.create_definition(payload)
    await record_audit(session, user, "definition.create", f"definition#{payload.name}",
                 {"type": payload.type, "source": "manual"})
    return created(definition)


@router.patch("/definitions/{name}/meta", response_model=ApiResponse[SpiderDefinitionResponse])
async def update_definition_meta(
    payload: DefinitionUpdateMetaRequest,
    name: str = Path(..., min_length=1, max_length=50),
    service: SpiderRegistryService = Depends(_registry_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[SpiderDefinitionResponse]:
    """编辑爬虫定义元信息（标题/描述；仅管理员）"""
    definition = await service.update_definition_meta(name, payload)
    await record_audit(session, user, "definition.update_meta", f"definition#{name}",
                 payload.model_dump(exclude_unset=True))
    return updated(definition)


@router.delete("/definitions/{name}", response_model=ApiResponse[dict])
async def delete_definition(
    name: str = Path(..., min_length=1, max_length=50),
    service: SpiderRegistryService = Depends(_registry_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[dict]:
    """删除爬虫定义（存在历史任务引用时拒绝；仅管理员）"""
    result = await service.delete_definition(name)
    await record_audit(session, user, "definition.delete", f"definition#{name}")
    return deleted(data=result)


# ----------------------------------------------------------------------
# 代理池健康管理（B3）
# ----------------------------------------------------------------------
@router.get("/proxy-health", response_model=ApiResponse[list[dict]])
async def get_proxy_health(
    _user: CurrentUser = Depends(require_operator),
) -> ApiResponse[list[dict]]:
    """代理评分排行（评分驱动的智能代理管理）"""
    from backend.services.proxy_health_service import ProxyHealthService

    service = ProxyHealthService()
    return ok(await service.get_proxy_health())
