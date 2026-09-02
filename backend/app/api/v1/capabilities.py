"""能力资产目录 API（P6 C2）——统一读路径（四类资产共用）"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import CurrentUser, require_login
from backend.app.responses import ok
from backend.services.capability_service import CapabilityService
from platform_core.db import get_async_db

router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> CapabilityService:
    return CapabilityService(session)


@router.get("")
async def list_capabilities(
    type: str = Query(None, description="skill/plugin/expert/expert_team"),
    category: str = Query(None),
    status: str = Query(None),
    q: str = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _user: CurrentUser = Depends(require_login),
    service: CapabilityService = Depends(_service),
):
    """统一资产列表（管理端）"""
    rows, total = await service.list_assets(
        asset_type=type, category=category, status=status, q=q,
        offset=(page - 1) * page_size, limit=page_size,
    )
    items = [
        {
            "id": r.id, "asset_type": r.asset_type, "name": r.name,
            "title": r.title or "", "description": r.description,
            "category": r.category, "status": r.status, "tier": r.tier,
            "score": float(r.score) if r.score is not None else None,
            "ai_suggested_score": float(r.ai_suggested_score) if r.ai_suggested_score is not None else None,
            "sync_state": r.sync_state,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]
    return ok(data={"total": total, "items": items})


@router.get("/{asset_type}/{name}")
async def get_capability_detail(
    asset_type: str,
    name: str,
    _user: CurrentUser = Depends(require_login),
    service: CapabilityService = Depends(_service),
):
    """统一详情（治理字段 + 类型化细节由各域端点补充）"""
    asset = await service.get_asset(asset_type, name)
    return ok(data={
        "id": asset.id, "asset_type": asset.asset_type, "name": asset.name,
        "title": asset.title, "description": asset.description,
        "category": asset.category, "status": asset.status, "tier": asset.tier,
        "source_url": asset.source_url, "source_author": asset.source_author,
        "score": float(asset.score) if asset.score is not None else None,
        "ai_suggested_score": float(asset.ai_suggested_score) if asset.ai_suggested_score is not None else None,
        "similar_to": asset.similar_to, "file_path": asset.file_path,
        "sync_state": asset.sync_state,
    })
