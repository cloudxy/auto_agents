"""把 .agents 同步进能力市场：listed+stable，hash 未变则跳过。

feat-agents-market：非破坏单通道（FR-01）——只 insert/update，无 deleted_at 写路径；
并发兜底 = DB uq_asset_type_name_alive + IntegrityError 降级 unchanged（GWT-01.7）；
actor=manual|startup 进 sync_completed/sync_failed 事件（GWT-08.3）。
失源行清理（FR-02）= 对账差剪除：prune_missing_assets 显式治理动作，可重复。
"""
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import and_, exists, not_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config_consts import SKILLS_AGENTS_ROOT
from backend.services.market_events import emit_sync_completed, emit_sync_failed
from backend.services.power_market.agents_hub_scan import HubItem, collect_agents_hub
from backend.services.power_market.types import MERGED_PLUGIN_NAME
from platform_core.logger import get_logger
from platform_core.models.capability import (
    CapabilityAsset, CapabilityCommand, CapabilityExpert, CapabilityPlugin,
)

logger = get_logger("service.power_market")
_DESC_MAX = 1024
_LICENSE_OK = "MIT"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def agents_root() -> Path:
    """落盘真相源 .agents 根（SKILLS.AGENTS_ROOT；相对路径按 cwd 解析）。"""
    logger.info("agents_hub.agents_root | resolve")
    from config import settings

    raw = str(settings.get("SKILLS.AGENTS_ROOT", SKILLS_AGENTS_ROOT) or SKILLS_AGENTS_ROOT)
    root = Path(raw)
    return root if root.is_absolute() else Path.cwd() / root


# FR-02 对账范围：.agents 四类磁盘源资产（team 人工定义、源注册表行不进对账）
_RECONCILE_TYPES = ("skill", "plugin", "command", "agent")


def _expert_legacy_clause():
    """expert 遗留型排除谓词（QA-7R）：agent ∩ 有侧行 ∩ file_path 非 .agents 前缀。

    侧行分量不可省：hub 入库对每个同步 agent 行都建侧行（agents_hub._upsert_agent），
    仅 EXISTS 会把全部 hub agent 行永久排除出 prune 候选；file_path 前缀才是
    legacy/hub 判别式。file_path IS NOT NULL 分量显式归一化三值逻辑——
    NULL file_path 必须落「非排除」侧（QA-14 裁定：视为可清），裸 NOT NULL
    传播会让 NOT(谓词) 整体为 NULL 而误排除。
    """
    return and_(
        CapabilityAsset.asset_type == "agent",
        exists(
            select(CapabilityExpert.id).where(
                CapabilityExpert.asset_id == CapabilityAsset.id
            )
        ),
        CapabilityAsset.file_path.is_not(None),
        CapabilityAsset.file_path.not_like(".agents/%"),
    )


async def prune_missing_assets(
    session: AsyncSession, agents_root, *, dry_run: bool = False,
) -> dict:
    """失源行清理（FR-02）：对账差剪除，显式治理动作（同步通道永不隐式软删）。

    候选 = live ∩ 四类 ∩ source_id IS NULL ∩ 非 expert 遗留型；
    磁盘集 = collect_agents_hub 的 (asset_type, name)；
    剪除 = 候选 − 磁盘集 → deleted_at=now, sync_state='gone'。
    dry_run=True 返回同构预览不落库（QA-9）。幂等：二次执行 pruned=[]（GWT-02.4）。
    """
    logger.info(f"agents_hub.prune_missing_assets | root={agents_root} dry_run={dry_run}")
    disk = {(i.asset_type, i.name) for i in collect_agents_hub(Path(agents_root))}
    rows = (await session.execute(
        select(CapabilityAsset).where(
            CapabilityAsset.deleted_at.is_(None),
            CapabilityAsset.source_id.is_(None),
            CapabilityAsset.asset_type.in_(_RECONCILE_TYPES),
            not_(_expert_legacy_clause()),
        ).order_by(CapabilityAsset.asset_type.asc(), CapabilityAsset.name.asc())
    )).scalars().all()
    live_before = len(rows)
    pruned: list[dict] = []
    now = _utcnow()
    for row in rows:
        if (row.asset_type, row.name) in disk:
            continue
        pruned.append({"asset_type": row.asset_type, "name": row.name})
        if not dry_run:
            row.deleted_at = now
            row.sync_state = "gone"
    if not dry_run:
        await session.flush()
    logger.info(
        f"agents_hub.prune done | pruned={len(pruned)} live_before={live_before} "
        f"disk={len(disk)} dry_run={dry_run}"
    )
    return {
        "pruned": pruned,
        "live_total": live_before - len(pruned),
        "disk_total": len(disk),
        "dry_run": bool(dry_run),
    }


async def sync_agents_hub(session: AsyncSession, agents_root, *, actor: str = "manual") -> dict:
    logger.info(f"agents_hub.sync | root={agents_root} actor={actor}")
    try:
        # 并发兜底（GWT-01.7，AD-2）：并发同步撞 uq_asset_type_name_alive →
        # IntegrityError 冒泡到本层，整轮回滚后重试一轮（重试轮读到的即对方
        # 已落的行 → 记 unchanged/updated）。sync 非破坏幂等，重放安全。
        # 注：per-item savepoint 吞键在本栈不可恢复（flush 失败会把异常写进
        # 外层事务 _rollback_exception，后续语句全部 PendingRollbackError，
        # 最小复现已核实）——故采用「整轮回滚 + 重试」实现同一 DB uq 兜底语义。
        for attempt in (1, 2):
            try:
                return await _sync_loop(session, Path(agents_root), actor)
            except IntegrityError as exc:
                logger.warning(
                    f"agents_hub 并发撞唯一键，回滚重试 | attempt={attempt} err={exc}"
                )
                await session.rollback()
        raise RuntimeError("agents_hub 同步连续两轮撞唯一键，请稍后重试")
    except Exception as exc:  # noqa: BLE001 sync_failed 事件后按原异常上抛
        error_type = type(exc).__name__
        logger.error(f"agents_hub.sync failed | actor={actor} error={exc}")
        await emit_sync_failed(session, actor=actor, error_type=error_type)
        raise


async def _sync_loop(session: AsyncSession, root: Path, actor: str) -> dict:
    items = collect_agents_hub(root)
    inserted = updated = unchanged = failed = 0
    failed_items: list[dict] = []
    for item in items:
        try:
            action = await _upsert_item(session, item)
        except IntegrityError:
            raise  # 撞键冒泡到 sync_agents_hub 重试层（不按单项失败计）
        except Exception as exc:  # noqa: BLE001 单项失败不中断
            failed += 1
            failed_items.append({"name": item.name, "type": item.asset_type, "reason": str(exc)})
            logger.warning(f"agents_hub 失败 | type={item.asset_type} name={item.name} err={exc}")
            continue
        if action == "inserted":
            inserted += 1
        elif action == "updated":
            updated += 1
        else:
            unchanged += 1
    await session.flush()
    logger.info(
        f"agents_hub.sync done | inserted={inserted} updated={updated} "
        f"unchanged={unchanged} failed={failed}"
    )
    await emit_sync_completed(
        session, actor=actor, added=inserted, updated=updated, unchanged=unchanged,
    )
    return {
        "inserted": inserted, "updated": updated, "unchanged": unchanged,
        "failed": failed, "failed_items": failed_items, "total": len(items),
    }


async def _upsert_item(session: AsyncSession, item: HubItem) -> str:
    """同步通道 upsert：上架态由 .agents 真相源决定（merged 插件恒 unlisted）。"""
    listing = "unlisted" if item.name == MERGED_PLUGIN_NAME else "listed"
    return await _apply_upsert(session, item, listing, keep_existing_listing=False)


async def _upsert_item_listing(
    session: AsyncSession, item: HubItem, *, listing: str,
) -> str:
    """导入通道 upsert（AD-4e）：新建行按 listing 落地（默认 unlisted，导入不自动
    上架）；已存在行**保留其现有上架态**——重导一个已上架资产不得把它下架。
    """
    return await _apply_upsert(session, item, listing, keep_existing_listing=True)


async def _apply_upsert(
    session: AsyncSession, item: HubItem, listing: str, *, keep_existing_listing: bool,
) -> str:
    row = await _load(session, item.asset_type, item.name)
    if row is not None and keep_existing_listing:
        listing = row.listing_state or listing
    desired = _desired(item, listing)
    if row is None:
        row = CapabilityAsset(asset_type=item.asset_type, name=item.name, **desired)
        if listing == "listed":
            row.listed_at = _utcnow()
        session.add(row)
        await session.flush()
        await _upsert_detail(session, row, item)
        return "inserted"
    if _same(row, desired):
        return "unchanged"
    entering = (row.listing_state or "") != listing and listing == "listed"
    for key, value in desired.items():
        setattr(row, key, value)
    if entering and row.listed_at is None:
        row.listed_at = _utcnow()
    await _upsert_detail(session, row, item)
    return "updated"


def _desired(item: HubItem, listing: str) -> dict:
    return {
        "title": item.title, "description": (item.description or "")[:_DESC_MAX] or None,
        "category": item.category, "status": "stable", "source_type": "self_built",
        "listing_state": listing, "writable": 1, "tenant_id": None, "sync_state": "ok",
        "license": (item.license or _LICENSE_OK)[:64],
        "file_path": item.file_path, "content_hash": item.content_hash,
        "origin_ref": item.origin_ref, "origin_local_name": item.origin_local_name,
        "origin_plugin_name": item.origin_plugin_name,
        "logo": item.logo, "background": item.background,
    }


def _same(row: CapabilityAsset, desired: dict) -> bool:
    for key, value in desired.items():
        if getattr(row, key) != value:
            return False
    return True


async def _load(session: AsyncSession, asset_type: str, name: str) -> CapabilityAsset | None:
    return (await session.execute(
        select(CapabilityAsset).where(
            CapabilityAsset.asset_type == asset_type,
            CapabilityAsset.name == name,
            CapabilityAsset.deleted_at.is_(None),
        )
    )).scalar_one_or_none()


async def _upsert_detail(session: AsyncSession, row: CapabilityAsset, item: HubItem) -> None:
    if item.asset_type == "plugin":
        await _upsert_plugin(session, row, item)
    elif item.asset_type == "command":
        await _upsert_command(session, row, item)
    elif item.asset_type == "agent":
        await _upsert_agent(session, row, item)


async def _upsert_plugin(session: AsyncSession, row: CapabilityAsset, item: HubItem) -> None:
    detail = (await session.execute(
        select(CapabilityPlugin).where(CapabilityPlugin.asset_id == row.id)
    )).scalar_one_or_none()
    if detail is None:
        detail = CapabilityPlugin(asset_id=row.id)
        session.add(detail)
    manifest = item.extra.get("manifest") or {}
    detail.manifest = manifest
    detail.version = str(manifest.get("version") or "")
    author = manifest.get("author") or {}
    detail.author = str(author.get("name", "")) if isinstance(author, dict) else str(author)
    detail.license = str(manifest.get("license") or item.license or "")
    # 类型化细节列与旧 scan-plugins 通道同口径（verify_plugin 管线读 mcp_servers，
    # 治理详情读 bundled_skills/hooks/commands——不回退能力）
    detail.bundled_skills = item.extra.get("bundled_skills") or []
    detail.mcp_servers = manifest.get("mcpServers") or manifest.get("mcp_servers") or {}
    detail.hooks = manifest.get("hooks") or {}
    detail.commands = manifest.get("commands") or {}
    await session.flush()


async def _upsert_command(session: AsyncSession, row: CapabilityAsset, item: HubItem) -> None:
    detail = (await session.execute(
        select(CapabilityCommand).where(CapabilityCommand.asset_id == row.id)
    )).scalar_one_or_none()
    slash = str(item.extra.get("slash") or item.origin_local_name)[:64]
    if detail is None:
        detail = CapabilityCommand(asset_id=row.id, slash=slash)
        session.add(detail)
    detail.slash = slash
    detail.description = item.description or None
    detail.body_md = item.extra.get("body_md") or None
    await session.flush()


async def _upsert_agent(session: AsyncSession, row: CapabilityAsset, item: HubItem) -> None:
    detail = (await session.execute(
        select(CapabilityExpert).where(CapabilityExpert.asset_id == row.id)
    )).scalar_one_or_none()
    if detail is None:
        detail = CapabilityExpert(asset_id=row.id)
        session.add(detail)
    detail.persona_md = item.extra.get("persona_md") or ""
    detail.tools = item.extra.get("tools") or []
    await session.flush()
