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


# ---------- P6 C3/C4：插件域（扫描/详情/验证） ----------


@router.post("/scan-plugins")
async def scan_plugins(
    _user: CurrentUser = Depends(require_login),
    session: AsyncSession = Depends(get_async_db),
):
    """扫描 capability-library/plugins/（plugin.json 解析入库）"""
    from backend.services.plugin_service import PluginService

    result = await PluginService(session).scan_plugins()
    return ok(data=result)


@router.get("/plugins/{name}")
async def get_plugin(
    name: str,
    _user: CurrentUser = Depends(require_login),
    session: AsyncSession = Depends(get_async_db),
):
    """插件详情（manifest/mcp_servers/健康态）"""
    from backend.services.plugin_service import PluginService

    return ok(data=await PluginService(session).get_plugin_detail(name))


@router.post("/plugins/{name}/verify")
async def verify_plugin(
    name: str,
    user: CurrentUser = Depends(require_login),
    session: AsyncSession = Depends(get_async_db),
):
    """插件验证管线（ADR-0001）：MCP 连接→tools/list→抽样 call→健康落库"""
    from backend.app.api._helpers import record_audit
    from backend.services.plugin_service import PluginService

    result = await PluginService(session).verify_plugin(name)
    await record_audit(session, user, "plugin.verify", f"plugin#{name}",
                       detail={"health": result["health"]})
    return ok(data=result)


# ---------- P6 C5/C6：专家域（扫描/详情/组队） ----------


@router.post("/scan-experts")
async def scan_experts(
    _user: CurrentUser = Depends(require_login),
    session: AsyncSession = Depends(get_async_db),
):
    """扫描 capability-library/experts/（subagent 格式解析入库）"""
    from backend.services.expert_service import ExpertService

    result = await ExpertService(session).scan_experts()
    return ok(data=result)


@router.get("/experts/{name}")
async def get_expert(
    name: str,
    _user: CurrentUser = Depends(require_login),
    session: AsyncSession = Depends(get_async_db),
):
    """专家详情（persona/tools/skills/mcp）"""
    from backend.services.expert_service import ExpertService

    return ok(data=await ExpertService(session).get_expert_detail(name))


@router.post("/teams")
async def upsert_team(
    body: dict,
    user: CurrentUser = Depends(require_login),
    session: AsyncSession = Depends(get_async_db),
):
    """专家团定义（团长/成员引用校验；执行引擎二期）"""
    from backend.app.api._helpers import record_audit
    from backend.services.expert_service import TeamService

    team = await TeamService(session).upsert_team(
        name=str(body.get("name") or ""),
        leader=str(body.get("leader") or ""),
        members=[str(m) for m in (body.get("members") or [])],
        workflow_md=str(body.get("workflow_md") or ""),
        title=str(body.get("title") or ""),
    )
    await record_audit(session, user, "team.upsert", f"team#{team['name']}")
    return ok(data=team)


@router.get("/teams/{name}")
async def get_team(
    name: str,
    _user: CurrentUser = Depends(require_login),
    session: AsyncSession = Depends(get_async_db),
):
    """专家团详情"""
    from backend.services.expert_service import TeamService

    return ok(data=await TeamService(session).get_team_detail(name))


@router.get("/teams/{name}/export")
async def export_team(
    name: str,
    _user: CurrentUser = Depends(require_login),
    session: AsyncSession = Depends(get_async_db),
):
    """专家团导出（TEAM.md 文档形态）"""
    from backend.services.expert_service import TeamService

    return ok(data={"markdown": await TeamService(session).export_team_md(name)})
