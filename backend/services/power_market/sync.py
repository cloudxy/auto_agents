"""src_sync：upsert 目录，第三方新行 unlisted；同源再同步不改 listing；撞插件名失败。"""
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config_consts import POWER_MARKET_SRC_SYNC_LOCK_TTL
from backend.services.market_events import (
    MARKET_SOURCE_SYNC_COMPLETED, emit_market_event,
)
from backend.services.power_market.identity import (
    SOURCE_INDEXED,
    _bundled_slug,
    _display_title,
    _path_slug,
)
from backend.services.power_market.sources import SourceRegistry, _project_source
from backend.services.power_market.types import (
    MSG_PLUGIN_COLLISION,
    SYNC_IN_PROGRESS_CODE,
)
from backend.services.power_market.walk import (
    _fold_commands, _fold_skills, _iter_packages, _read_manifest,
)
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger
from platform_core.models.capability import (
    CapabilityAsset, CapabilityCommand, CapabilityPlugin, CapabilitySource,
)
from platform_core.models.skill import SkillJob

logger = get_logger("service.power_market")
_DESC_MAX = 1024


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SourceSync:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.registry = SourceRegistry(session)

    async def sync(self, name: str) -> dict:
        logger.info(f"power_market.src_sync | source={name}")
        cm = await _try_sync_lock(name)
        async with cm as lock:
            if lock is None:
                raise BusinessException(
                    message="同步进行中", code=SYNC_IN_PROGRESS_CODE, status_code=409,
                )
            return await self._sync_locked(name)

    async def _sync_locked(self, name: str) -> dict:
        source = await self.registry.get_source(name)
        job = SkillJob(
            job_type="src_sync", status="running", total=0, succeeded=0, failed=0,
            source_id=source.id,
        )
        self.session.add(job)
        await self.session.flush()
        job_id = int(job.id)
        result = await self._run_packages(source)
        job.total = result["total"]
        job.succeeded = result["succeeded"]
        job.failed = result["failed"]
        job.status = "done"
        job.detail = {"failed": result["failed_items"]}
        job.finished_at = _utcnow()
        source.last_sync_at = _utcnow()
        source.last_succeeded = result["succeeded"]
        source.last_failed = result["failed"]
        source.last_error = (result["failed_items"][0]["reason"] if result["failed_items"] else None)
        result["job_id"] = job_id
        result["source"] = _project_source(source)
        await self.session.commit()
        await emit_market_event(
            self.session, MARKET_SOURCE_SYNC_COMPLETED,
            props={"succeeded": result["succeeded"], "failed": result["failed"]},
        )
        return result

    async def _run_packages(self, source: CapabilitySource) -> dict:
        root = Path(source.uri).expanduser()
        packages = _iter_packages(root)
        succeeded, failed = 0, 0
        failed_items: list[dict] = []
        keeps: dict[str, dict[str, set[str]]] = {}
        for pkg in packages:
            try:
                keeps[pkg.name] = await self._sync_package(source, pkg)
                succeeded += 1
            except Exception as exc:  # noqa: BLE001 单包失败不中断
                failed += 1
                failed_items.append({"name": pkg.name, "reason": str(exc)})
                logger.warning(f"源同步包失败 | source={source.name} pkg={pkg.name} err={exc}")
        retracted = await self._retract_missing_rows(
            source, {pkg.name for pkg in packages}, keeps,
        )
        return {
            "total": len(packages), "succeeded": succeeded, "failed": failed,
            "failed_items": failed_items, "retracted": retracted,
        }

    async def _sync_package(
        self, source: CapabilitySource, pkg: Path,
    ) -> dict[str, set[str]]:
        manifest = _read_manifest(pkg)
        plugin_name = pkg.name
        await self._upsert_plugin(source, pkg, plugin_name, manifest)
        skill_keep = await self._upsert_skills(source, pkg, plugin_name)
        command_keep = await self._upsert_commands(source, pkg, plugin_name, manifest)
        return {"skill": skill_keep, "command": command_keep}

    async def _load_named(self, asset_type: str, name: str) -> CapabilityAsset | None:
        return (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == asset_type,
                CapabilityAsset.name == name,
                CapabilityAsset.deleted_at.is_(None),
            )
        )).scalar_one_or_none()

    async def _upsert_plugin(
        self, source: CapabilitySource, pkg: Path, plugin_name: str, manifest: dict,
    ) -> CapabilityAsset:
        row = await self._load_named("plugin", plugin_name)
        if row is not None and row.source_id not in (None, source.id):
            raise BusinessException(message=MSG_PLUGIN_COLLISION, code="PLUGIN_NAME_COLLISION")
        title = str(manifest.get("description") or plugin_name)[:_DESC_MAX]
        if row is None:
            row = CapabilityAsset(
                asset_type="plugin", name=plugin_name, title=title,
                category="plugin", status="experimental",
                source_type=SOURCE_INDEXED, listing_state="unlisted",
                writable=0, tenant_id=None, sync_state="ok",
                license=str(manifest.get("license") or "") or None,
            )
            self.session.add(row)
            await self.session.flush()
        self._attach_third_party(row, source, origin_ref=plugin_name, local=plugin_name)
        row.title = title
        row.sync_state = "ok"
        await self._upsert_plugin_detail(row, manifest, pkg)
        return row

    def _attach_third_party(
        self, row: CapabilityAsset, source: CapabilitySource, *, origin_ref: str, local: str,
        parent: str | None = None, digest: str = "", aliases: list | None = None,
    ) -> None:
        first_attach = row.source_id is None or row.source_id != source.id
        row.source_id = source.id
        row.source_type = SOURCE_INDEXED
        row.writable = 0
        if first_attach:
            row.listing_state = "unlisted"
        row.origin_ref = origin_ref
        row.origin_local_name = local
        row.origin_plugin_name = parent
        row.content_hash = digest or (row.content_hash or "")
        if aliases:
            row.alias_origin_refs = aliases

    async def _upsert_plugin_detail(
        self, asset: CapabilityAsset, manifest: dict, pkg: Path,
    ) -> None:
        detail = (await self.session.execute(
            select(CapabilityPlugin).where(CapabilityPlugin.asset_id == asset.id)
        )).scalar_one_or_none()
        if detail is None:
            detail = CapabilityPlugin(asset_id=asset.id)
            self.session.add(detail)
        detail.version = str(manifest.get("version") or "")
        author = manifest.get("author") or {}
        detail.author = str(author.get("name", "")) if isinstance(author, dict) else str(author)
        detail.license = str(manifest.get("license") or "")
        detail.manifest = manifest
        skills_dir = pkg / "skills"
        bundled = []
        if skills_dir.is_dir():
            bundled = sorted(d.name for d in skills_dir.iterdir() if d.is_dir())
        detail.bundled_skills = bundled
        raw_cmds = manifest.get("commands")
        if isinstance(raw_cmds, (dict, list)):
            detail.commands = raw_cmds
        await self.session.flush()

    async def _upsert_skills(
        self, source: CapabilitySource, pkg: Path, plugin_name: str,
    ) -> set[str]:
        seen_locals: dict[str, str] = {}
        keep: set[str] = set()
        for item in _fold_skills(pkg):
            local = item["origin_local_name"]
            if local in seen_locals and seen_locals[local] != item["content_hash"]:
                name = _path_slug(plugin_name, item["origin_ref"])
            else:
                name = _bundled_slug(plugin_name, local)
                seen_locals[local] = item["content_hash"]
            keep.add(name)
            await self._upsert_skill_row(source, plugin_name, name, item)
        return keep

    async def _upsert_skill_row(
        self, source: CapabilitySource, plugin_name: str, name: str, item: dict,
    ) -> None:
        row = await self._load_named("skill", name)
        if row is not None and row.source_id not in (None, source.id):
            raise BusinessException(message=MSG_PLUGIN_COLLISION, code="PLUGIN_NAME_COLLISION")
        title = _display_title(item["origin_local_name"], item.get("title") or "")
        if row is None:
            row = CapabilityAsset(
                asset_type="skill", name=name, title=title,
                category="uncategorized", status="experimental",
                source_type=SOURCE_INDEXED, listing_state="unlisted",
                writable=0, tenant_id=None, sync_state="ok", license="MIT",
            )
            self.session.add(row)
            await self.session.flush()
        self._attach_third_party(
            row, source, origin_ref=item["origin_ref"], local=item["origin_local_name"],
            parent=plugin_name, digest=item["content_hash"],
            aliases=item.get("alias_origin_refs") or None,
        )
        row.title = title
        row.file_path = item.get("file_path") or row.file_path
        await self.session.flush()

    async def _upsert_commands(
        self, source: CapabilitySource, pkg: Path, plugin_name: str, manifest: dict,
    ) -> set[str]:
        keep: set[str] = set()
        for item in _fold_commands(pkg, manifest):
            name = _bundled_slug(plugin_name, item["origin_local_name"])
            keep.add(name)
            await self._upsert_command_row(source, plugin_name, name, item)
        return keep

    async def _retract_missing_rows(
        self, source: CapabilitySource, package_names: set[str],
        keeps: dict[str, dict[str, set[str]]],
    ) -> dict[str, int]:
        """源里已经没有的行：软删收回，不再出现在治理目录/公开商店（FR-88）。

        命令同构扩到技能/插件；整包删除时包内技能/命令随包收回（不残留
        孤儿行）。包还在但同步失败的（在 package_names、不在 keeps）保留
        不动——失败是解析/DB 问题，不是源删除，不能借同步失败收回活行。
        """
        counts = {"plugin": 0, "skill": 0, "command": 0}
        now = _utcnow()
        plugin_rows = (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == "plugin",
                CapabilityAsset.source_id == source.id,
                CapabilityAsset.deleted_at.is_(None),
            )
        )).scalars().all()
        for row in plugin_rows:
            if row.name in package_names:
                continue
            row.deleted_at = now
            row.sync_state = "gone"
            counts["plugin"] += 1
        child_rows = (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type.in_(("skill", "command")),
                CapabilityAsset.source_id == source.id,
                CapabilityAsset.deleted_at.is_(None),
            )
        )).scalars().all()
        for row in child_rows:
            parent = row.origin_plugin_name or ""
            if not parent:
                continue  # 无父行不属包收回范围
            if parent in keeps:
                if row.name in keeps[parent].get(row.asset_type, set()):
                    continue
            elif parent in package_names:
                continue
            row.deleted_at = now
            row.sync_state = "gone"
            counts[row.asset_type] += 1
        if any(counts.values()):
            logger.info(f"src_sync 收回缺失行: source={source.name} counts={counts}")
        return counts

    async def _upsert_command_row(
        self, source: CapabilitySource, plugin_name: str, name: str, item: dict,
    ) -> None:
        row = await self._load_named("command", name)
        if row is not None and row.source_id not in (None, source.id):
            raise BusinessException(message=MSG_PLUGIN_COLLISION, code="PLUGIN_NAME_COLLISION")
        title = _display_title(item["origin_local_name"], item.get("title") or "")
        if row is None:
            row = CapabilityAsset(
                asset_type="command", name=name, title=title,
                category="command", status="experimental",
                source_type=SOURCE_INDEXED, listing_state="unlisted",
                writable=0, tenant_id=None, sync_state="ok",
            )
            self.session.add(row)
            await self.session.flush()
        self._attach_third_party(
            row, source, origin_ref=item["origin_ref"], local=item["origin_local_name"],
            parent=plugin_name, digest=item.get("content_hash") or "",
        )
        row.title = title
        row.description = (item.get("description") or "")[:_DESC_MAX] or row.description
        row.file_path = item.get("file_path") or row.file_path
        await self._upsert_command_detail(row, item)

    async def _upsert_command_detail(self, asset: CapabilityAsset, item: dict) -> None:
        detail = (await self.session.execute(
            select(CapabilityCommand).where(CapabilityCommand.asset_id == asset.id)
        )).scalar_one_or_none()
        slash = (item.get("slash") or item["origin_local_name"])[:64]
        if detail is None:
            detail = CapabilityCommand(asset_id=asset.id, slash=slash)
            self.session.add(detail)
        detail.slash = slash
        detail.description = item.get("description") or None
        detail.body_md = item.get("body_md") or None
        await self.session.flush()


async def _try_sync_lock(source_name: str):
    """抢不到锁则拒绝第二同步；Redis 故障放行（测试/降级）。"""
    from config import settings

    from platform_core.redis_async import get_async_redis

    ttl = int(settings.get("POWER_MARKET.SRC_SYNC_LOCK_TTL", POWER_MARKET_SRC_SYNC_LOCK_TTL) or 900)
    key = f"market:src_sync:{source_name}"
    try:
        redis = get_async_redis()
        acquired = await redis.set(key, "1", nx=True, ex=ttl)
        if acquired is False:
            return _BusyLock()
        return _OwnedLock(redis, key)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"src_sync 锁不可用，放行 | source={source_name} err={exc}")
        return _NullLock()


class _NullLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _BusyLock:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *args):
        return False


class _OwnedLock:
    def __init__(self, redis, key: str):
        self.redis = redis
        self.key = key

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        try:
            await self.redis.delete(self.key)
        except Exception:  # noqa: BLE001
            return False
        return False
