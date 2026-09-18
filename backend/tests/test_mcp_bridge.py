"""C 线 53/54 验证：插件域扫描 + MCP 桥白名单/验证管线。

feat-agents-market AD-1：PluginService.scan_plugins 退役（破坏性扫描根因），
插件入库统一走 .agents 非破坏同步（agents_hub.sync_agents_hub）——本文件的
扫描路径用例已按新通道改写，覆盖同一断言面（manifest 解析 → plugin 资产行 +
CapabilityPlugin 细节行，含 mcp_servers/bundled_skills 投影）。
"""
import json

import pytest
from sqlalchemy import select

from backend.services.power_market.agents_hub import sync_agents_hub
from platform_core.models.capability import CapabilityAsset, CapabilityPlugin


@pytest.fixture
def agents_tree(tmp_path):
    """能力库根（SKILLS.AGENTS_ROOT 指到临时 .agents）"""
    from config import settings

    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(tmp_path))
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
    settings.set("SKILLS.AGENTS_ROOT", original)


@pytest.mark.asyncio
async def test_plugin_sync_and_crud(db_session, agents_tree):
    async with db_session() as s:
        result = await sync_agents_hub(s, agents_tree, actor="manual")
        await s.commit()

    assert result["failed"] == 0 and result["inserted"] >= 2

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

    assert asset.status == "stable"
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


def test_plugin_sync_bad_manifest_zero_rows(db_session, db_engine, tmp_path):
    """坏 plugin.json：collect 跳过该插件（无行、无 failed 噪音——非破坏通道不建错误行）"""
    import asyncio

    from config import settings

    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(tmp_path))
    d = tmp_path / "plugins" / "bad-plugin"
    d.mkdir(parents=True)
    (d / "plugin.json").write_text("{ not valid json")

    async def _sync():
        async with db_session() as s:
            result = await sync_agents_hub(s, tmp_path, actor="manual")
            await s.commit()
            return result

    result = asyncio.run(_sync())
    assert result["total"] == 0  # 坏清单插件零收集
    rows = asyncio.run(_q(db_session, select(CapabilityAsset)))
    assert rows == []
    settings.set("SKILLS.AGENTS_ROOT", original)


async def _q(db_session, stmt):
    async with db_session() as s:
        return list((await s.execute(stmt)).scalars().all())


@pytest.mark.asyncio
async def test_plugin_sync_zcode_nested_manifest(db_session, tmp_path):
    """zcode 布局（.zcode-plugin/plugin.json）+ 符号链接目录：同步跟源头，不复制内容"""
    from config import settings

    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(tmp_path))
    canonical = tmp_path / "canonical" / "sdlc-workflow"
    canonical.mkdir(parents=True)
    (canonical / ".zcode-plugin").mkdir()
    (canonical / ".zcode-plugin" / "plugin.json").write_text(json.dumps({
        "name": "sdlc-workflow", "version": "3.5.5", "description": "SDLC",
        "author": {"name": "xuyun"},
    }), encoding="utf-8")
    (canonical / "skills" / "pm").mkdir(parents=True)
    (canonical / "skills" / "pm" / "SKILL.md").write_text(
        "---\nname: pm\ndescription: pm\n---\n# pm\n", encoding="utf-8",
    )
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    (plugins_root / "sdlc-workflow").symlink_to(canonical)

    async with db_session() as s:
        result = await sync_agents_hub(s, tmp_path, actor="manual")
        await s.commit()

    assert result["failed"] == 0
    assert result["inserted"] >= 1

    async with db_session() as s:
        asset = (await s.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == "plugin",
                CapabilityAsset.name == "sdlc-workflow",
            )
        )).scalar_one()
        detail = (await s.execute(
            select(CapabilityPlugin).where(CapabilityPlugin.asset_id == asset.id)
        )).scalar_one()

    assert detail.version == "3.5.5"
    settings.set("SKILLS.AGENTS_ROOT", original)
