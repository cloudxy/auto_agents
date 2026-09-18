"""能力资产目录 API（P6 C2）——统一读路径（四类资产共用）

路由注册顺序约束（同 skills.py 防线）：二段式静态前缀路由
（/plugins/{name} /experts/{name} /teams/{name}）必须先于二段式动态路由
/{asset_type}/{name} 注册，否则后者把复数 asset_type（plugins/experts/teams）
当第一段吞掉，三条静态详情路由恒 404（B5 修复 B1c F-1）。
新增二段式路由一律置于 get_capability_detail（本文件末尾）之前。
"""
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import omit_local_abs_paths_for_non_platform_admin
from backend.app.api.deps import (
    CurrentUser,
    require_login,
    require_platform_admin_or_404,
)
from backend.app.responses import ok
from platform_core.exceptions import ValidationException
from backend.services.capability_service import CapabilityService
from backend.services.market_events import run_subscribe
from backend.services.power_market import (
    CorrectRequest,
    CreateSourceRequest,
    PowerMarketService,
    PatchLicenseOverrideRequest,
    PatchListingRequest,
    PutAliasRequest,
)
from backend.services.power_market.types import PatchInstallRequest, SubscribeRequest
from platform_core.db import get_async_db

router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> CapabilityService:
    return CapabilityService(session)


def _market(session: AsyncSession = Depends(get_async_db)) -> PowerMarketService:
    return PowerMarketService(session)


@router.get("")
async def list_capabilities(
    type: str = Query(None, description="skill/plugin/command/agent/team（expert/expert_team 一周期可读）"),
    category: str = Query(None),
    status: str = Query(None),
    listing_state: str = Query(None),
    q: str = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(require_login),
    service: CapabilityService = Depends(_service),
    market: PowerMarketService = Depends(_market),
):
    """超管=治理目录；租户=货架（关旗「能力市场未开放」，不含未上架）。"""
    if not user.is_platform_admin:
        return ok(data=await market.list_public(
            asset_type=type, category=category, q=q, page=page, page_size=page_size,
        ))
    return ok(data=await service.list_catalog(
        asset_type=type, category=category, status=status, q=q,
        listing_state=listing_state,
        offset=(page - 1) * page_size, limit=page_size,
    ))


# ---------- P6 C3/C4：插件域（扫描/详情/验证） ----------


@router.get("/sources")
async def list_capability_sources(
    user: CurrentUser = Depends(require_platform_admin_or_404),
    market: PowerMarketService = Depends(_market),
):
    """源列表。仅超管。"""
    return ok(data=await market.list_sources())


@router.post("/sources")
async def register_capability_source(
    payload: CreateSourceRequest,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
    market: PowerMarketService = Depends(_market),
):
    """登记源。url 类失败说明未支持。"""
    from backend.app.api._helpers import record_audit

    data = await market.register_source(payload, actor=user.username)
    await record_audit(user, "source.register", f"source#{data['name']}")
    return ok(data=data)


@router.post("/sources/{name}/sync")
async def sync_capability_source(
    name: str,
    retract: bool = Query(False, description="源里已经没有的行是否软删收回；缺省=只 upsert，不收回"),
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
    market: PowerMarketService = Depends(_market),
):
    """触发 src_sync。第三方新行保持 unlisted。

    QA-8：收回缺失行是破坏性动作，必须显式 `?retract=true` 才执行（与
    「同步通道默认永不隐式软删」的全局口径对齐）；不传时本次同步只
    upsert，源里消失的行原样保留待下次显式收回。
    """
    from backend.app.api._helpers import record_audit

    data = await market.sync_source(name, retract=retract)
    await record_audit(user, "source.sync", f"source#{name}",
        detail={
            "succeeded": data.get("succeeded"), "failed": data.get("failed"),
            "retract": retract,
        },
    )
    return ok(data=data)


@router.post("/backfill-first-party")
async def backfill_first_party_listing(
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
    market: PowerMarketService = Depends(_market),
):
    """第一方已发布/推荐 → listed；host_compat 保持 NULL。非迁移。"""
    from backend.app.api._helpers import record_audit

    data = await market.backfill_first_party()
    await record_audit(user, "source.backfill", "first-party", detail=data)
    return ok(data=data)


# feat-agents-market AD-1：破坏性扫描入口 POST /scan-plugins 已删除
# （软删根因 plugin_service._retract_missing_plugins 一并退役；.agents 同步走
#   capabilities_gov.sync_agents-hub，非破坏 upsert，GWT-01.3 验收线）。


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
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
):
    """插件验证管线（ADR-0001）：MCP 连接→tools/list→抽样 call→健康落库"""
    from backend.app.api._helpers import record_audit
    from backend.services.plugin_service import PluginService

    result = await PluginService(session).verify_plugin(name)
    await record_audit(user, "plugin.verify", f"plugin#{name}",
                       detail={"health": result["health"]})
    return ok(data=result)


# ---------- P6 C5/C6：专家域（详情/组队） ----------
# POST /scan-experts 已退役（K4）：扫的是 capability-library/experts/，OQ-2
# 切根到 .agents 后该目录已不存在于仓库，每次扫描恒空——保留端点只会让
# 管理员误以为「扫描成功、0 条」是正常结果。ExpertService.scan_experts()
# 方法本身保留（接受显式 root 参数，供内部/测试按需从任意目录导入专家）。


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
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
):
    """专家团定义（团长=专家；成员=专家∪智能体，T-37 / GWT-101；执行引擎不做）。

    越权 404 同形（GWT-101.5：租户直打与「页面不存在」同形，不走 403 信封）。
    members 兼容两种形态：名称字符串（按专家）或 {"type": "expert"|"agent", "name"}。
    """
    from backend.app.api._helpers import record_audit
    from backend.services.expert_service import TeamService

    team = await TeamService(session).upsert_team(
        name=str(body.get("name") or ""),
        leader=str(body.get("leader") or ""),
        members=body.get("members") or [],
        workflow_md=str(body.get("workflow_md") or ""),
        title=str(body.get("title") or ""),
    )
    await record_audit(user, "team.upsert", f"team#{team['name']}")
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


# ---------- 能力资产一键导入（FR-100 / ADR-0023，静态段先于动态段） ----------


@router.post("/import")
async def import_assets(
    file: list[UploadFile] = File(None),
    directory: str = Form(None),
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
):
    """统一导入通道（仅平台超管；非超管直打 404 同形，GWT-100.6）。

    multipart 文件（单 .md 或 zip 包，可多选）**或**服务器本地目录路径；
    沙箱解包 + 四类判定分发（skill/agent/command/plugin，GWT-100.4）；
    部分成功逐条中文原因（100.2/100.3）；超大拒绝含上限数字（100.5）；
    路径逃逸条目拒绝且资产目录外零新文件（100.7，NFR-04/SEC-11）；
    幂等=类型+名称（100.8）；产物未上架、不触发执行（PC-2）；完成上报
    asset_imported（GWT-92.9）。
    """
    from backend.app.api._helpers import record_audit
    from backend.services.asset_import_service import AssetImportService

    payloads = [(f.filename or "upload", await f.read()) for f in (file or [])]
    if directory and payloads:
        raise ValidationException(message="文件与目录只能二选一", field="import")
    service = AssetImportService(session)
    if directory:
        data = await service.import_directory(directory, actor=user.username, actor_id=user.id)
    elif payloads:
        data = await service.import_files(payloads, actor=user.username, actor_id=user.id)
    else:
        raise ValidationException(message="未提供导入文件或目录", field="import")
    await record_audit(user, "asset.import", f"batch#{data['batch_id']}",
        detail={"origin": data["origin"], "succeeded": data["succeeded"],
                "failed": data["failed"], "skipped": data["skipped"]},
    )
    return ok(data=data)


# ---------- 订阅 / 安装行（静态段必须先于 /{asset_type}/{name}） ----------


@router.get("/installs")
async def list_capability_installs(
    user: CurrentUser = Depends(require_login),
    market: PowerMarketService = Depends(_market),
):
    """本企业安装行（T-25 可查询；T-26 展示/卸载）。"""
    return ok(data=await market.list_installs(user))


@router.patch("/installs/{install_id}")
async def patch_capability_install(
    install_id: int,
    payload: PatchInstallRequest,
    user: CurrentUser = Depends(require_login),
    market: PowerMarketService = Depends(_market),
):
    """改启用/信任。黑名单/软删行只读这两列；只读角色走 MARKET_READONLY_ROLE。"""
    return ok(data=await market.patch_install(install_id, user, payload))


@router.delete("/installs/{install_id}")
async def delete_capability_install(
    install_id: int,
    user: CurrentUser = Depends(require_login),
    market: PowerMarketService = Depends(_market),
):
    """软删这一行。不沿合集边级联。unlist/黑名单经办可卸。"""
    return ok(data=await market.uninstall(install_id, user))


@router.post("/{asset_type}/{name}/correct")
async def correct_capability_asset(
    asset_type: str,
    name: str,
    payload: CorrectRequest,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
    market: PowerMarketService = Depends(_market),
):
    """D5：第三方纠正不可用，不写源树。"""
    from backend.app.api._helpers import record_audit

    body = payload.model_dump(exclude_none=True)
    data = await market.correct_asset(asset_type, name, body)
    await record_audit(user, "asset.correct", f"{asset_type}#{name}")
    return ok(data=data)


@router.patch("/{asset_type}/{name}/listing")
async def patch_capability_listing(
    asset_type: str,
    name: str,
    payload: PatchListingRequest,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
    market: PowerMarketService = Depends(_market),
):
    """上架三态。与验证/治理 status 分闸。listed_at unlist 不清空。"""
    from backend.app.api._helpers import record_audit

    data = await market.set_listing(asset_type, name, payload)
    await record_audit(user, "listing.change", f"{asset_type}#{name}",
        detail={"listing_state": data["listing_state"]},
    )
    return ok(data=data)


@router.patch("/{asset_type}/{name}/license-override")
async def patch_license_override(
    asset_type: str,
    name: str,
    payload: PatchLicenseOverrideRequest,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
    market: PowerMarketService = Depends(_market),
):
    """特例放行。仅超管。收回不拆已订行与引用解析。"""
    from backend.app.api._helpers import record_audit

    data = await market.set_license_override(asset_type, name, payload)
    await record_audit(user, "license.override", f"{asset_type}#{name}",
        detail={"public_license_override": data["public_license_override"]},
    )
    return ok(data=data)


@router.put("/{asset_type}/{name}/alias")
async def put_capability_alias(
    asset_type: str,
    name: str,
    payload: PutAliasRequest,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
    market: PowerMarketService = Depends(_market),
):
    """指定/改人工短名。仅超管。撞存活目录短名或存活 alias → 409。"""
    from backend.app.api._helpers import record_audit

    data = await market.set_alias(asset_type, name, payload, actor=user.username)
    await record_audit(user, "alias.set", f"{asset_type}#{name}",
        detail={"slug": data["slug"]},
    )
    return ok(data=data)


@router.post("/{asset_type}/{name}/subscribe")
async def subscribe_capability(
    asset_type: str,
    name: str,
    payload: SubscribeRequest | None = None,
    user: CurrentUser = Depends(require_login),
    market: PowerMarketService = Depends(_market),
):
    """订这一行到一个宿主。不礼包、不占三类配额。"""
    host = payload.host if payload else None
    data = await run_subscribe(
        market.session, market, asset_type=asset_type, name=name, host=host, user=user,
    )
    return ok(data=data)


@router.get("/{asset_type}/{name}/references")
async def list_capability_references(
    asset_type: str,
    name: str,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    market: PowerMarketService = Depends(_market),
):
    """超管/系统引用列表（FR-36）。忽略子行 listing；黑名单/软删跳过并审计。"""
    return ok(data=await market.list_runtime_references(asset_type, name, user=user))


# ---------- 统一详情（动态段，必须最后注册，见文件头顺序约束） ----------


@router.get("/{asset_type}/{name}")
async def get_capability_detail(
    asset_type: str,
    name: str,
    user: CurrentUser = Depends(require_login),
    service: CapabilityService = Depends(_service),
):
    """统一详情（治理字段 + 类型化细节由各域端点补充）

    注意：本路由为二段式动态段，必须保持在文件末尾注册，否则遮蔽
    /plugins/{name} /experts/{name} /teams/{name} 三条静态详情路由（恒 404）。
    非超管不发出本机绝对路径（GWT-14.1/14.2）；相对库路径可保留。
    """
    asset = await service.get_asset(asset_type, name)
    data = {
        "id": asset.id, "asset_type": asset.asset_type, "name": asset.name,
        "title": asset.title, "description": asset.description,
        "category": asset.category, "status": asset.status, "tier": asset.tier,
        "source_url": asset.source_url, "source_author": asset.source_author,
        "score": float(asset.score) if asset.score is not None else None,
        "ai_suggested_score": float(asset.ai_suggested_score) if asset.ai_suggested_score is not None else None,
        "similar_to": asset.similar_to, "file_path": asset.file_path,
        "sync_state": asset.sync_state,
        "listing_state": asset.listing_state,
        "listed_at": asset.listed_at.isoformat() if asset.listed_at else None,
        "source_type": asset.source_type,
    }
    return ok(data=omit_local_abs_paths_for_non_platform_admin(data, user))
