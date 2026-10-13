""" .agents 增量同步：新行插入、hash 不变跳过、内容变了才更新。"""
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.services.power_market.agents_hub import sync_agents_hub
from platform_core.models.capability import CapabilityAsset

_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def _write(path: Path, text: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")


def _tree(root: Path) -> Path:
    agents = root / ".agents"
    # D2：游离 skill 只有 frontmatter 声明了允许集许可才会被同步自动上架（不再默认 MIT）
    _write(agents / "skills" / "demo-skill" / "SKILL.md", """---
name: demo-skill
description: First party demo skill.
license: MIT
---
# demo
""")
    _write(agents / "skills" / "demo-skill" / "icon.png", _PNG)
    _write(agents / "skills" / "demo-skill" / "background.png", _PNG)
    _write(agents / "plugins" / "demo-plug" / "plugin.json", """{
  "name": "demo-plug",
  "description": "Demo plugin",
  "license": "MIT",
  "commands": "commands"
}
""")
    _write(agents / "plugins" / "demo-plug" / "skills" / "inner" / "SKILL.md", """---
name: inner
description: Bundled skill.
---
# inner
""")
    _write(agents / "plugins" / "demo-plug" / "commands" / "do.md", """---
name: do
description: Do the thing.
---
# do
""")
    _write(agents / "plugins" / "demo-plug" / "commands" / "do.icon.png", _PNG)
    _write(agents / "plugins" / "demo-plug" / "agents" / "bot.md", """---
name: bot
description: A demo agent.
tools: Read, Write
---
You are bot.
""")
    _write(agents / "plugins" / "demo-plug" / "agents" / "profiles" / "bot" / "icon.png", _PNG)
    _write(
        agents / "plugins" / "demo-plug" / "agents" / "profiles" / "bot" / "background.png",
        _PNG,
    )
    return agents


@pytest.mark.asyncio
async def test_hub_inserts_then_noop_on_second_sync(db_session, tmp_path):
    agents = _tree(tmp_path)
    async with db_session() as session:
        first = await sync_agents_hub(session, agents)
        await session.commit()
    assert first["failed"] == 0
    assert first["inserted"] >= 5
    assert first["updated"] == 0
    async with db_session() as session:
        second = await sync_agents_hub(session, agents)
        await session.commit()
        rows = (await session.execute(select(CapabilityAsset))).scalars().all()
    assert second["inserted"] == 0
    assert second["updated"] == 0
    assert second["unchanged"] == first["inserted"]
    by_type = {r.asset_type: r for r in rows}
    skill = next(r for r in rows if r.name == "demo-skill")
    assert skill.listing_state == "listed"
    assert skill.status == "stable"
    assert skill.logo and skill.logo.endswith("icon.png")
    assert skill.background and skill.background.endswith("background.png")
    assert "plugin" in by_type
    assert any(r.asset_type == "command" and r.logo for r in rows)
    assert any(r.asset_type == "agent" and r.background for r in rows)


@pytest.mark.asyncio
async def test_hub_updates_when_skill_md_changes(db_session, tmp_path):
    agents = _tree(tmp_path)
    async with db_session() as session:
        await sync_agents_hub(session, agents)
        await session.commit()
    md = agents / "skills" / "demo-skill" / "SKILL.md"
    md.write_text(md.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
    async with db_session() as session:
        result = await sync_agents_hub(session, agents)
        await session.commit()
        skill = (await session.execute(
            select(CapabilityAsset).where(CapabilityAsset.name == "demo-skill")
        )).scalar_one()
    assert result["updated"] >= 1
    assert result["inserted"] == 0
    assert skill.content_hash
    assert skill.listing_state == "listed"


# ---------- D2：许可缺失不再默认 MIT，也不被同步自动上架 ----------


def _bare_tree(root: Path) -> Path:
    """全无许可声明的 hub 树：游离 skill + 插件（含 bundled skill / command / agent）。"""
    hub = root / "hub"
    _write(hub / "skills" / "nolic" / "SKILL.md", "---\nname: nolic\ndescription: d\n---\n# x\n")
    _write(hub / "plugins" / "bare-plug" / "plugin.json", '{"name": "bare-plug", "description": "d"}')
    _write(hub / "plugins" / "bare-plug" / "skills" / "inner" / "SKILL.md",
           "---\nname: inner\ndescription: d\n---\n# i\n")
    _write(hub / "plugins" / "bare-plug" / "commands" / "go.md", "---\nname: go\n---\n# go\n")
    _write(hub / "plugins" / "bare-plug" / "agents" / "bot.md", "---\nname: bot\n---\nYou are bot.\n")
    return hub


async def _rows_by_name(db_session) -> dict[str, CapabilityAsset]:
    async with db_session() as session:
        rows = (await session.execute(select(CapabilityAsset))).scalars().all()
    return {r.name: r for r in rows}


@pytest.mark.asyncio
async def test_d2_missing_license_is_unknown_and_not_auto_listed(db_session, tmp_path):
    from backend.services.power_market.agents_hub_scan import collect_agents_hub

    hub = _bare_tree(tmp_path)
    items = collect_agents_hub(hub)
    assert len(items) == 5 and all(i.license == "" for i in items)  # 不再假定 MIT
    async with db_session() as session:
        result = await sync_agents_hub(session, hub)
        await session.commit()
    rows = await _rows_by_name(db_session)
    assert result["failed"] == 0 and result["inserted"] == 5
    assert all(r.license is None for r in rows.values())  # NULL = 未声明
    assert all(r.listing_state == "unlisted" and r.listed_at is None for r in rows.values())
    assert all(r.status == "stable" for r in rows.values())


@pytest.mark.asyncio
async def test_d2_bundled_assets_inherit_plugin_license_and_gate_by_allowed_set(db_session, tmp_path):
    hub = _bare_tree(tmp_path)
    _write(hub / "plugins" / "bare-plug" / "plugin.json",
           '{"name": "bare-plug", "description": "d", "license": "Apache-2.0"}')
    _write(hub / "skills" / "gpl" / "SKILL.md", "---\nname: gpl\nlicense: GPL-3.0\n---\n# g\n")
    async with db_session() as session:
        await sync_agents_hub(session, hub)
        await session.commit()
    rows = await _rows_by_name(db_session)
    for name in ("bare-plug", "bare-plug__inner", "bare-plug__go", "bare-plug__bot"):
        assert (rows[name].license, rows[name].listing_state) == ("Apache-2.0", "listed"), name
    assert (rows["gpl"].license, rows["gpl"].listing_state) == ("GPL-3.0", "unlisted")  # 不在允许集
    assert (rows["nolic"].license, rows["nolic"].listing_state) == (None, "unlisted")


@pytest.mark.asyncio
async def test_d2_resync_corrects_assumed_mit_and_respects_override(db_session, tmp_path):
    """D2 前同步把无许可资产记成 MIT 并上架：重同步改回未声明并下架；
    超管已开 public_license_override 的行与公开许可闸同口径，保持上架。"""
    hub = _bare_tree(tmp_path)
    async with db_session() as session:
        await sync_agents_hub(session, hub)
        for row in (await session.execute(select(CapabilityAsset))).scalars().all():
            row.license, row.listing_state = "MIT", "listed"  # 模拟 D2 前存量
            row.public_license_override = 1 if row.name == "bare-plug" else 0
        await session.commit()
    async with db_session() as session:
        result = await sync_agents_hub(session, hub)
        await session.commit()
    rows = await _rows_by_name(db_session)
    assert result["updated"] == 5 and result["failed"] == 0
    assert all(r.license is None for r in rows.values())
    assert rows["bare-plug"].listing_state == "listed"
    assert all(r.listing_state == "unlisted" for n, r in rows.items() if n != "bare-plug")
