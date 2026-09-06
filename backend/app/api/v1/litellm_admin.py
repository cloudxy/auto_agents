"""LiteLLM 治理 API：平台超管经 Admin API 管虚拟键，禁直连其库。"""
from typing import Any

from fastapi import APIRouter, Depends

from backend.app.api.deps import require_platform_admin
from backend.app.responses import ApiResponse, created, ok
from backend.services.litellm.admin_service import LiteLlmAdminService
from platform_core.schemas.litellm import LitellmKeyCreate, LitellmKeyOut

router = APIRouter()


def _svc() -> LiteLlmAdminService:
    return LiteLlmAdminService()


@router.get("/keys", response_model=ApiResponse[list[dict[str, Any]]])
async def list_litellm_keys(
    _user=Depends(require_platform_admin),
    service: LiteLlmAdminService = Depends(_svc),
) -> ApiResponse[list[dict[str, Any]]]:
    return ok(await service.list_keys())


@router.post("/keys", response_model=ApiResponse[LitellmKeyOut], status_code=201)
async def create_litellm_key(
    payload: LitellmKeyCreate,
    _user=Depends(require_platform_admin),
    service: LiteLlmAdminService = Depends(_svc),
) -> ApiResponse[LitellmKeyOut]:
    return created(await service.create_key(payload))


@router.delete("/keys", response_model=ApiResponse[None])
async def delete_litellm_key(
    key: str,
    _user=Depends(require_platform_admin),
    service: LiteLlmAdminService = Depends(_svc),
) -> ApiResponse[None]:
    await service.delete_key(key)
    return ok(None)


@router.get("/spend", response_model=ApiResponse[list[dict[str, Any]]])
async def litellm_spend(
    _user=Depends(require_platform_admin),
    service: LiteLlmAdminService = Depends(_svc),
) -> ApiResponse[list[dict[str, Any]]]:
    return ok(await service.spend_logs())
