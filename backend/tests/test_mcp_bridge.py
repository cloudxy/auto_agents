"""C 线 53/54 验证：插件域扫描 + MCP 桥白名单/验证管线"""
import json

import pytest
from sqlalchemy import select

from platform_core.models.capability import CapabilityAsset, CapabilityPlugin


@pytest.fixture
def plugin_library(tmp_path):
    from config import settings

    original = settings.get("SKILLS.LIBRARY_ROOT")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))
    d = tmp_path / "plugins" / "demo-tool"
    d.mkdir(parents=True)
    (d / "plugin.json").write_text(json.dumps({
        "name": "demo-tool", "version": "1.0.0", "description": "演示插件",
        "author": {"name": "test"}, "license": "MIT", "skills": "skills",
        "mcpServers": {"demo": {"command": "node", "args": ["server.js"]}},
    }))
    (d / "skills" / "sub-skill").mkdir(parents=True)
    (d / "skills" / "sub-skill" / "SKILL.md").write_text("---\nname: sub-skill\n---\n# S\n")
    yield tmp_path
    settings.set("SKILLS.LIBRARY_ROOT", original)


@pytest.mark.asyncio
async def test_plugin_scan_and_crud(db_session, plugin_library):
    from backend.services.plugin_service import PluginService

    async with db_session() as s:
        result = await PluginService(s).scan_plugins(root=plugin_library / "plugins")
        await s.commit()

    assert result["total"] == 1 and result["failed"] == 0

    async with db_session() as s:
        asset = (await s.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == "plugin",
                CapabilityAsset.name == "demo-tool",
            )
        )).scalar_one()
        detail = (await s.execute(
            select(CapabilityPlugin).where(CapabilityPlugin.asset_id == asset.id)
        )).scalar_one()

    assert asset.status == "experimental"
    assert detail.version == "1.0.0"
    assert detail.mcp_servers == {"demo": {"command": "node", "args": ["server.js"]}}
    assert detail.health_status == "unknown"


@pytest.mark.asyncio
async def test_mcp_stdio_whitelist_rejects_arbitrary():
    """白名单外可执行文件拒绝（ADR-0001 安全边界）"""
    from backend.services.mcp_bridge import list_tools

    result = await list_tools({"command": "/bin/sh", "args": ["-c", "echo pwned"]})
    assert result["ok"] is False
    assert "白名单" in result["error"]


@pytest.mark.asyncio
async def test_verify_pipeline_down_on_connect_failure():
    from backend.services.mcp_bridge import verify_plugin_server

    result = await verify_plugin_server(
        {"command": "python3", "args": ["-c", "import sys; sys.exit(1)"]}
    )
    assert result["health"] == "down"


def test_plugin_scan_bad_manifest_marked(db_client, db_engine, db_session, tmp_path):
    import asyncio

    from config import settings

    original = settings.get("SKILLS.LIBRARY_ROOT")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))
    d = tmp_path / "plugins" / "bad-plugin"
    d.mkdir(parents=True)
    (d / "plugin.json").write_text("{ not valid json")

    async def _scan():
        from backend.services.plugin_service import PluginService

        async with db_session() as s:
            result = await PluginService(s).scan_plugins(root=tmp_path / "plugins")
            await s.commit()
            return result

    result = asyncio.run(_scan())
    assert result["failed"] == 1 and "bad-plugin" in result["failed_names"]
    settings.set("SKILLS.LIBRARY_ROOT", original)
