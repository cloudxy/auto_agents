"""LLM 供应商管理接口（阶段二）—— API 层只做参数校验与 Service 编排，不碰 ORM/Session

前端契约（已对齐）：
- GET /llm/providers 信封 data=[...]（全量数组，无分页），api_key 恒为掩码字段 api_key_masked
- PUT 时 api_key 留空表示不修改
- test 信封 data={ok, latency_ms, model, error}，不落库（探测结论 data.ok 与信封
  success 语义正交，ADR-001 刻意不白名单）
响应契约：统一 ApiResponse 信封（ADR-001）。
GET 类端点 require_login；写操作（POST/PUT/DELETE/activate/test）require_admin 并审计。
"""
from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, require_admin, require_login
from backend.app.responses import ApiResponse, created, deleted, ok, updated
from backend.services.llm_provider_service import LlmProviderService
from platform_core.db import get_async_db
from platform_core.schemas.llm_provider import (
    LlmProviderCreate,
    LlmProviderResponse,
    LlmProviderTestResponse,
    LlmProviderUpdate,
)

router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> LlmProviderService:
    return LlmProviderService(session)


@router.get("/providers", response_model=ApiResponse[list[LlmProviderResponse]])
async def list_providers(
    service: LlmProviderService = Depends(_service),
    _user: CurrentUser = Depends(require_login),
) -> ApiResponse[list[LlmProviderResponse]]:
    """LLM 供应商全量列表（信封 data=[...]；api_key 恒为掩码 api_key_masked）"""
    return ok(await service.list_providers())


@router.get("/providers/active", response_model=ApiResponse[LlmProviderResponse])
async def get_active_provider(
    service: LlmProviderService = Depends(_service),
    _user: CurrentUser = Depends(require_login),
) -> ApiResponse[LlmProviderResponse]:
    """当前激活的 LLM 供应商（无激活行 404，此时运行时配置走 yml/env 兜底）"""
    return ok(await service.get_active_provider())


@router.post("/providers", response_model=ApiResponse[LlmProviderResponse])
async def create_provider(
    payload: LlmProviderCreate,
    service: LlmProviderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[LlmProviderResponse]:
    """创建 LLM 供应商（仅管理员；api_key 落库为 Fernet 密文，未配置主密钥时拒绝保存）"""
    item = await service.create_provider(payload)
    await record_audit(session, user, "llm.provider.create", f"llm_provider#{item.id}",
                       {"name": item.name})
    return created(item)


@router.put("/providers/{provider_id}", response_model=ApiResponse[LlmProviderResponse])
async def update_provider(
    payload: LlmProviderUpdate,
    provider_id: int = Path(..., ge=1),
    service: LlmProviderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[LlmProviderResponse]:
    """更新 LLM 供应商（仅管理员；PATCH 语义，api_key 留空不修改）"""
    item = await service.update_provider(provider_id, payload)
    await record_audit(session, user, "llm.provider.update", f"llm_provider#{provider_id}")
    return updated(item)


@router.delete("/providers/{provider_id}", response_model=ApiResponse[dict])
async def delete_provider(
    provider_id: int = Path(..., ge=1),
    service: LlmProviderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[dict]:
    """删除 LLM 供应商（仅管理员；激活位随行删除，无激活行时运行时配置走 yml/env 兜底）"""
    result = await service.delete_provider(provider_id)
    await record_audit(session, user, "llm.provider.delete", f"llm_provider#{provider_id}")
    return deleted(data=result)


@router.put("/providers/{provider_id}/activate", response_model=ApiResponse[LlmProviderResponse])
async def activate_provider(
    provider_id: int = Path(..., ge=1),
    service: LlmProviderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[LlmProviderResponse]:
    """激活热切换（仅管理员；单激活互斥，目标行置 active、其余清零）"""
    item = await service.activate_provider(provider_id)
    await record_audit(session, user, "llm.provider.activate", f"llm_provider#{provider_id}")
    return updated(item)


@router.post("/providers/{provider_id}/test", response_model=ApiResponse[LlmProviderTestResponse])
async def test_provider_connectivity(
    provider_id: int = Path(..., ge=1),
    service: LlmProviderService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[LlmProviderTestResponse]:
    """连通性测试（仅管理员；一次性 10s client 发 1-token 请求，结果不落库）"""
    result = await service.test_connectivity(provider_id)
    await record_audit(session, user, "llm.provider.test", f"llm_provider#{provider_id}",
                       {"ok": result.ok})
    return ok(result)
