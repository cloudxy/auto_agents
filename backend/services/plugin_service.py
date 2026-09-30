"""插件资产域服务（P6 C3）：plugin.json 解析 + 插件详情 + MCP 验证

feat-agents-market AD-1：破坏性扫描入口 scan_plugins / _retract_missing_plugins
已退役（.agents 软删 bug 根因，FR-01 验收线 = 不存在能造成软删的扫描入口）。
扫描/同步统一走 power_market.agents_hub（.agents 真相源，非破坏 upsert）。
"""
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.exceptions import NotFoundException
from platform_core.logger import get_logger
from platform_core.models.capability import CapabilityAsset, CapabilityPlugin
from platform_core.timeutil import utc_iso

logger = get_logger("service.plugin")

_DESCRIPTION_MAX = 1024
# 根级 plugin.json 优先；否则认各 host 的嵌套清单（zcode / Claude Code / Grok）。
_MANIFEST_CANDIDATES = (
    "plugin.json",
    ".zcode-plugin/plugin.json",
    ".claude-plugin/plugin.json",
    ".grok-plugin/plugin.json",
)


def _plugin_manifest_path(plugin_dir: Path) -> Optional[Path]:
    for rel in _MANIFEST_CANDIDATES:
        path = plugin_dir / rel
        if path.is_file():
            return path
    return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_REDACTED = "******"
_SECRET_ARG = re.compile(r"(?i)(token|secret|password|passwd|api[-_]?key|auth)")


def redact_mcp_servers(servers: dict) -> dict:
    """MCP 配置脱敏：env / headers 只保留键名；args 中形如 --api-key=xxx 的值打码

    插件清单里的 env 常携带第三方凭据（审计 BUG-45），任何人都不应经 API 读到明文；
    键名保留，便于判断需要配置哪些变量。
    """
    logger.debug(f"MCP 配置脱敏 | servers={len(servers) if isinstance(servers, dict) else 0}")
    if not isinstance(servers, dict):
        return {}
    out: dict = {}
    for server_name, cfg in servers.items():
        if not isinstance(cfg, dict):
            out[server_name] = cfg
            continue
        item = dict(cfg)
        for key in ("env", "headers"):
            if isinstance(item.get(key), dict):
                item[key] = {k: _REDACTED for k in item[key]}
        if isinstance(item.get("args"), list):
            args, mask_next = [], False
            for arg in item["args"]:
                text = str(arg)
                if mask_next:
                    args.append(_REDACTED)
                    mask_next = False
                    continue
                if "=" in text and _SECRET_ARG.search(text.split("=", 1)[0]):
                    args.append(text.split("=", 1)[0] + "=" + _REDACTED)
                    continue
                if text.startswith("-") and _SECRET_ARG.search(text):
                    mask_next = True
                args.append(arg)
            item["args"] = args
        out[server_name] = item
    return out


class PluginService:
    """插件域（session 注入）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_plugin_detail(self, name: str) -> dict:
        """插件详情（asset + detail 投影；mcp_servers 的 env/headers 值一律脱敏，审计 BUG-45）"""
        from backend.services.capability_lookup import find_named_asset

        logger.info(f"查询插件详情 | name={name}")
        asset = await find_named_asset(self.session, "plugin", name)
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
            "mcp_servers": redact_mcp_servers((detail.mcp_servers if detail else {}) or {}),
            "hooks_registered": bool((detail.hooks if detail else {}) or {}),
            "commands_registered": bool((detail.commands if detail else {}) or {}),
            "health_status": detail.health_status if detail else "unknown",
            "listing_state": asset.listing_state,
            "listed_at": utc_iso(asset.listed_at),
            "source_type": asset.source_type,
            "last_verified_at": (
                utc_iso(detail.last_verified_at) if detail and detail.last_verified_at else None
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
            detail.health_status = "unknown"
            detail.verify_detail = {"error": "插件未声明 MCP servers（无可验证工具链）"}
            detail.last_verified_at = _utcnow()
            await self.session.flush()
            result = {"health": "unknown", "detail": dict(detail.verify_detail)}
            await self.session.commit()
            return result

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
        detail.verify_detail = {"servers": results, "verified_at": utc_iso(_utcnow())}
        detail.last_verified_at = _utcnow()
        await self.session.flush()
        await self.session.commit()
        return {"health": overall, "detail": results}
