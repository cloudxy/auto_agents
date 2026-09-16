"""能力资产治理动作路由（feat-agents-market）——.agents 单通道治理面。

本文件承载契约 §4 的治理端点（避免 capabilities.py 458 行贴线破 500 上限）：
- POST /capabilities/sync-agents-hub        手动同步 .agents（非破坏，FR-01）
- POST /capabilities/assets/prune-missing   失源行清理（FR-02，T-03 落地）
- POST /capabilities/import/tree/preview    目录导入预览（FR-07，T-07 落地）
- POST /capabilities/import/tree/confirm    目录导入确认（FR-07，T-07 落地）
- PATCH /capabilities/{t}/{n}/featured      精选开关（FR-04，T-06 落地）
- PATCH /capabilities/{t}/{n}/examples      示例维护（附加 d，T-06 落地）

全部挂 require_platform_admin_or_404（越权 404 存在性隐藏门面，GWT-01.5 等）。
挂载顺序约束：本路由必须在 capabilities.router 之前 include（capabilities.py 的
二段式动态段 /{asset_type}/{name} 会吞掉本文件静态段路由，见其文件头）。
"""
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import CurrentUser, require_platform_admin_or_404
from backend.app.responses import ok
from backend.services.power_market.curation import (
    PatchExamplesRequest,
    PatchFeaturedRequest,
)
from platform_core.db import get_async_db
from platform_core.logger import get_logger

logger = get_logger("api")

router = APIRouter()


@router.post("/sync-agents-hub")
async def sync_agents_hub(
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
):
    """手动同步 .agents → capability_assets（非破坏 upsert；仅平台超管）。

    重复触发幂等（GWT-01.2）；任何失败路径不软删行（GWT-01.3）；
    失败上抛 → 统一异常处理器 500 + sync_failed 事件（GWT-08.3）。
    """
    from backend.app.api._helpers import record_audit
    from backend.services.power_market.agents_hub import (
        agents_root as hub_agents_root, sync_agents_hub as run_sync,
    )

    logger.info(f"capabilities_gov.sync_agents_hub | user={user.username}")
    data = await run_sync(session, hub_agents_root(), actor="manual")
    await session.commit()
    await record_audit(
        session, user, "agents_hub.sync", ".agents",
        detail={"total": data.get("total"), "inserted": data.get("inserted"),
                "updated": data.get("updated"), "failed": data.get("failed")},
    )
    return ok(data=data)


@router.post("/assets/prune-missing")
async def prune_missing_assets(
    dry_run: bool = Query(False, description="true=同构预览不落库（QA-9）"),
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
):
    """失源行清理（FR-02；仅平台超管）：live 行 − 磁盘可识别集 → 软删。

    排除 team/源注册表行/expert 遗留型（QA-7R 判别式见 agents_hub）；幂等；
    dry_run=true 返回执行态同构 pruned 预览且不写 deleted_at。
    """
    from backend.app.api._helpers import record_audit
    from backend.services.power_market.agents_hub import (
        agents_root as hub_agents_root, prune_missing_assets as run_prune,
    )

    logger.info(
        f"capabilities_gov.prune_missing_assets | user={user.username} dry_run={dry_run}"
    )
    data = await run_prune(session, hub_agents_root(), dry_run=dry_run)
    if not dry_run:
        await session.commit()
    await record_audit(
        session, user, "assets.prune_missing", ".agents",
        detail={"pruned": len(data.get("pruned") or []),
                "live_total": data.get("live_total"),
                "disk_total": data.get("disk_total"), "dry_run": dry_run},
    )
    return ok(data=data)


@router.patch("/{asset_type}/{name}/featured")
async def patch_capability_featured(
    asset_type: str,
    name: str,
    payload: PatchFeaturedRequest,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
):
    """精选开关（FR-04 / GWT-04.5；仅平台超管，越权 404）。

    同步不重置本列（agents_hub._desired 白名单不含 featured，db-spec §9）。
    """
    from backend.app.api._helpers import record_audit
    from backend.services.power_market.curation import set_featured

    logger.info(
        f"capabilities_gov.patch_featured | user={user.username} "
        f"type={asset_type} name={name} featured={payload.featured}"
    )
    data = await set_featured(session, asset_type, name, payload.featured)
    await record_audit(
        session, user, "asset.featured", f"{asset_type}#{name}",
        detail={"featured": data["featured"]},
    )
    return ok(data=data)


@router.patch("/{asset_type}/{name}/examples")
async def patch_capability_examples(
    asset_type: str,
    name: str,
    payload: PatchExamplesRequest,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
):
    """详情示例区维护（附加 d / AD-7；仅平台超管，越权 404）。

    上限 20 条 × 200 字由 PatchExamplesRequest 校验（超限 422）；
    空列表 = 取消维护 → 详情投影空列表 → 前端隐藏区块（GWT-05.3）。
    """
    from backend.app.api._helpers import record_audit
    from backend.services.power_market.curation import set_examples

    logger.info(
        f"capabilities_gov.patch_examples | user={user.username} "
        f"type={asset_type} name={name} n={len(payload.examples)}"
    )
    data = await set_examples(session, asset_type, name, payload.examples)
    await record_audit(
        session, user, "asset.examples", f"{asset_type}#{name}",
        detail={"count": len(data["examples"])},
    )
    return ok(data=data)


async def _read_parts(files: list[UploadFile]) -> list:
    """把 multipart part 读成服务层的 UploadedFile（filename=webkitRelativePath）。"""
    from backend.services.power_market.hub_import import UploadedFile

    out = []
    for part in files or []:
        out.append(UploadedFile(
            filename=part.filename or "", content=await part.read(),
        ))
    return out


@router.post("/import/tree/preview")
async def preview_tree_import_endpoint(
    files: list[UploadFile] = File(...),
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
):
    """目录导入预览（FR-07 / AD-4d；仅平台超管，越权 404）。

    不写库不落盘：判型清单 + 跳过清单 + 四类计数；取消 = 不发 confirm。
    """
    from backend.services.power_market.hub_import import preview_tree_import

    logger.info(
        f"capabilities_gov.preview_tree_import | user={user.username} parts={len(files or [])}"
    )
    data = await preview_tree_import(session, await _read_parts(files))
    return ok(data=data)


@router.post("/import/tree/confirm")
async def confirm_tree_import_endpoint(
    files: list[UploadFile] = File(...),
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
):
    """目录导入确认（FR-07 / AD-4e；仅平台超管，越权 404）。

    落盘统一 .agents + upsert 入库；单项失败入 failed 清单不整批回滚（GWT-07.5）；
    成功发 import_completed、异常发 import_failed 后按原异常上抛（GWT-08.1/08.2）。
    """
    from backend.app.api._helpers import record_audit
    from backend.services.market_events import emit_import_completed, emit_import_failed
    from backend.services.power_market.agents_hub import agents_root as hub_agents_root
    from backend.services.power_market.hub_import import confirm_tree_import

    logger.info(
        f"capabilities_gov.confirm_tree_import | user={user.username} parts={len(files or [])}"
    )
    parts = await _read_parts(files)
    try:
        data = await confirm_tree_import(session, parts, agents_root=hub_agents_root())
    except Exception as exc:  # noqa: BLE001 先发 import_failed 再按原异常上抛
        await emit_import_failed(
            session, actor_role=user.role or "", error_type=type(exc).__name__,
            actor_user_id=user.id,
        )
        raise
    await session.commit()
    await emit_import_completed(
        session, actor_role=user.role or "", source="directory", files=len(parts),
        assets_created=data["created"], assets_updated=data["updated"],
        assets_skipped=len(data["skipped"]), actor_user_id=user.id,
    )
    await record_audit(
        session, user, "assets.import_tree", ".agents",
        detail={"created": data["created"], "updated": data["updated"],
                "failed": len(data["failed"]), "skipped": len(data["skipped"])},
    )
    return ok(data=data)
