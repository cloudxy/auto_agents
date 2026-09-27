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
    _write(agents / "skills" / "demo-skill" / "SKILL.md", """---
name: demo-skill
description: First party demo skill.
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
