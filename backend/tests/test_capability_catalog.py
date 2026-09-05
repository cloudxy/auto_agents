"""C 线 52 验证：资产目录契约（capability_assets + skills 回填 + GET /capabilities）"""
import asyncio

import pytest
from sqlalchemy import select

from backend.services.skill_service import SkillService
from platform_core.models.capability import CapabilityAsset
from platform_core.models.skill import Skill


@pytest.fixture
def library_root(tmp_path):
    from config import settings

    original = settings.get("SKILLS.LIBRARY_ROOT")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))
    d = tmp_path / "skills" / "asset-skill"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: asset-skill\ndescription: 测试\n---\n# A\n")
    (d / "meta.yaml").write_text("name: asset-skill\ncategory: test-cat\nstatus: stable\n")
    yield tmp_path
    settings.set("SKILLS.LIBRARY_ROOT", original)


@pytest.mark.asyncio
async def test_scan_backfills_asset_row(db_session, library_root):
    """技能扫描后自动回填 capability_assets 行（type=skill, detail_id 挂钩）"""
    async with db_session() as s:
        await SkillService(s).scan_library(root=library_root / "skills")
        await s.commit()

    async with db_session() as s:
        asset = (await s.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == "skill",
                CapabilityAsset.name == "asset-skill",
            )
        )).scalar_one()
        skill = (await s.execute(select(Skill).where(Skill.name == "asset-skill"))).scalar_one()

    assert asset.category == "test-cat"
    assert asset.status == "stable"
    assert asset.detail_id == skill.id  # 细节表挂钩


def test_get_capabilities_api(db_client, admin_client, db_engine, db_session, library_root):
    asyncio.run(_scan(db_session, library_root))
    resp = db_client.get("/api/v1/capabilities", params={"type": "skill"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 1
    assert any(i["name"] == "asset-skill" for i in data["items"])


async def _scan(db_session, library_root):
    async with db_session() as s:
        await SkillService(s).scan_library(root=library_root / "skills")
        await s.commit()
