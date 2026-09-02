"""插件资产域服务（P6 C3）：plugin.json 解析 + 扫描入库 + CRUD + MCP 验证"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.exceptions import NotFoundException, ValidationException
from platform_core.logger import get_logger
from platform_core.models.capability import CapabilityAsset, CapabilityPlugin
from platform_core.models.skill import SkillJob

logger = get_logger("service.plugin")

_DESCRIPTION_MAX = 1024


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PluginService:
    """插件域（session 注入）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def scan_plugins(self, root: Optional[Path] = None) -> dict:
        """扫描 capability-library/plugins/：解析 plugin.json → asset + detail upsert"""
        from config import settings

        if root is None:
            library_root = Path(str(settings.get("SKILLS.LIBRARY_ROOT", "capability-library")))
            root = library_root / "plugins"
        root = Path(root)

        job = SkillJob(job_type="scan_plugins", status="running", total=0, succeeded=0, failed=0)
        self.session.add(job)
        await self.session.flush()

        dirs = sorted(d for d in root.iterdir() if d.is_dir()) if root.exists() else []
        succeeded, failed = 0, 0
        failed_names: list[str] = []
        for plugin_dir in dirs:
            try:
                await self._upsert_from_dir(plugin_dir, root)
                succeeded += 1
            except Exception as exc:  # noqa: BLE001 单插件失败不中断整批
                failed += 1
                failed_names.append(plugin_dir.name)
                logger.warning(f"插件解析失败 | dir={plugin_dir.name} err={exc}")

        job.total, job.succeeded, job.failed, job.status = len(dirs), succeeded, failed, "done"
        job.detail = {"failed": failed_names}
        await self.session.flush()
        return {"total": len(dirs), "succeeded": succeeded, "failed": failed,
                "failed_names": failed_names, "job_id": job.id}

    async def _upsert_from_dir(self, plugin_dir: Path, root: Path) -> CapabilityAsset:
        manifest_path = plugin_dir / "plugin.json"
        if not manifest_path.exists():
            raise ValidationException(message=f"plugin.json 缺失: {plugin_dir.name}", field="url")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValidationException(message=f"plugin.json 非法 JSON: {exc}", field="url") from exc
        if not isinstance(manifest, dict) or not manifest.get("name"):
            raise ValidationException(message="plugin.json 缺 name", field="url")

        name = str(manifest["name"])
        if name != plugin_dir.name:
            logger.warning(f"插件名与目录名不一致（以目录名为准）: manifest={name} dir={plugin_dir.name}")
            name = plugin_dir.name

        # 内嵌技能（bundled skills）：列出 skills/ 子目录名（不递归入 skills 表——它们随插件分发）
        bundled = []
        skills_dir = plugin_dir / "skills"
        if skills_dir.is_dir():
            bundled = sorted(d.name for d in skills_dir.iterdir() if d.is_dir())

        mcp_servers = manifest.get("mcpServers") or manifest.get("mcp_servers") or {}
        hooks = manifest.get("hooks") or {}
        commands = manifest.get("commands") or {}

        asset = (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == "plugin", CapabilityAsset.name == name
            )
        )).scalar_one_or_none()
        if asset is None:
            asset = CapabilityAsset(
                asset_type="plugin", name=name,
                title=str(manifest.get("description") or "")[:_DESCRIPTION_MAX],
                category="plugin", status="experimental",
                source_type="self_built",
                file_path=plugin_dir.relative_to(root.parent).as_posix(),
                sync_state="ok",
            )
            self.session.add(asset)
            await self.session.flush()
        else:
            asset.title = str(manifest.get("description") or "")[:_DESCRIPTION_MAX]
            asset.sync_state = "ok"

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
        detail.bundled_skills = bundled
        detail.mcp_servers = mcp_servers
        detail.hooks = hooks
        detail.commands = commands
        await self.session.flush()
        return asset

    async def get_plugin_detail(self, name: str) -> dict:
        """插件详情（asset + detail 投影）"""
        asset = (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == "plugin", CapabilityAsset.name == name
            )
        )).scalar_one_or_none()
        if asset is None:
            raise NotFoundException(resource=f"插件 {name}")
        detail = (await self.session.execute(
            select(CapabilityPlugin).where(CapabilityPlugin.asset_id == asset.id)
        )).scalar_one_or_none()
        return {
            "name": asset.name, "title": asset.title, "status": asset.status,
            "version": detail.version if detail else "",
            "author": detail.author if detail else "",
            "license": detail.license if detail else "",
            "bundled_skills": (detail.bundled_skills if detail else []) or [],
            "mcp_servers": (detail.mcp_servers if detail else {}) or {},
            "hooks_registered": bool((detail.hooks if detail else {}) or {}),
            "commands_registered": bool((detail.commands if detail else {}) or {}),
            "health_status": detail.health_status if detail else "unknown",
            "last_verified_at": (
                detail.last_verified_at.isoformat() if detail and detail.last_verified_at else None
            ),
            "verify_detail": detail.verify_detail if detail else None,
        }

    async def verify_plugin(self, name: str) -> dict:
        """插件验证管线（ADR-0001）：MCP 连接→list→抽样 call→健康落库"""
        from backend.services.mcp_bridge import verify_plugin_server

        logger.info(f"插件验证 | plugin={name}")
        asset = (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == "plugin", CapabilityAsset.name == name
            )
        )).scalar_one_or_none()
        if asset is None:
            raise NotFoundException(resource=f"插件 {name}")
        detail = (await self.session.execute(
            select(CapabilityPlugin).where(CapabilityPlugin.asset_id == asset.id)
        )).scalar_one_or_none()
        if detail is None:
            raise NotFoundException(resource=f"插件详情 {name}")

        servers = detail.mcp_servers or {}
        if not servers:
            detail.health_status = "degraded"
            detail.verify_detail = {"error": "插件未声明 MCP servers（无可验证工具链）"}
            detail.last_verified_at = _utcnow()
            await self.session.flush()
            return {"health": "degraded", "detail": detail.verify_detail}

        # 逐 server 验证；任一 healthy 即 healthy，全部 down 才 down
        results = {}
        overall = "down"
        for server_name, cfg in servers.items():
            if not isinstance(cfg, dict):
                continue
            results[server_name] = await verify_plugin_server(cfg)
            if results[server_name]["health"] == "healthy":
                overall = "healthy"
            elif results[server_name]["health"] == "degraded" and overall == "down":
                overall = "degraded"

        detail.health_status = overall
        detail.verify_detail = {"servers": results, "verified_at": _utcnow().isoformat()}
        detail.last_verified_at = _utcnow()
        await self.session.flush()
        return {"health": overall, "detail": results}
