"""C 线 55/56 验证：专家域（subagent 解析）+ 专家团定义层"""
import pytest
from sqlalchemy import select

from platform_core.models.capability import CapabilityAsset, CapabilityExpert


@pytest.fixture
def expert_library(tmp_path):
    from config import settings

    original = settings.get("SKILLS.LIBRARY_ROOT")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))
    d = tmp_path / "experts" / "code-reviewer"
    d.mkdir(parents=True)
    (d / "AGENT.md").write_text(
        "---\n"
        "name: code-reviewer\n"
        "description: 代码评审专家\n"
        "tools: [Read, Grep, Bash]\n"
        "skills: [coding-style]\n"
        "model: glm-4.7\n"
        "---\n"
        "你是资深代码评审员。\n"
        "评审时关注：安全性、可维护性、性能。\n"
    )
    yield tmp_path
    settings.set("SKILLS.LIBRARY_ROOT", original)


@pytest.mark.asyncio
async def test_expert_scan_subagent_format(db_session, expert_library):
    from backend.services.expert_service import ExpertService

    async with db_session() as s:
        result = await ExpertService(s).scan_experts(root=expert_library / "experts")
        await s.commit()
    assert result["succeeded"] == 1

    async with db_session() as s:
        asset = (await s.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == "expert",
                CapabilityAsset.name == "code-reviewer",
            )
        )).scalar_one()
        detail = (await s.execute(
            select(CapabilityExpert).where(CapabilityExpert.asset_id == asset.id)
        )).scalar_one()

    assert asset.title == "代码评审专家"
    assert detail.tools == ["Read", "Grep", "Bash"]
    assert detail.bundled_skills == ["coding-style"]
    assert detail.model_pref == "glm-4.7"
    assert "资深代码评审员" in detail.persona_md


@pytest.mark.asyncio
async def test_team_crud_and_dangling_ref(db_session, expert_library):
    from backend.services.expert_service import ExpertService, TeamService

    async with db_session() as s:
        await ExpertService(s).scan_experts(root=expert_library / "experts")
        await s.commit()

    # 悬空引用 → 422
    async with db_session() as s:
        from platform_core.exceptions import ValidationException

        with pytest.raises(ValidationException, match="不存在"):
            await TeamService(s).upsert_team(
                "review-team", leader="code-reviewer", members=["ghost-expert"])

    # 正常组队
    async with db_session() as s:
        team = await TeamService(s).upsert_team(
            "review-team", leader="code-reviewer",
            members=["code-reviewer"],  # 单成员自组团（测试简化）
            workflow_md="团长拆解 → 并行评审 → 汇总")
        await s.commit()
        assert team.name == "review-team"

        exported = await TeamService(s).export_team_md("review-team")
    assert "团长" in exported and "code-reviewer" in exported


@pytest.mark.asyncio
async def test_expert_skill_bundle_validation(db_session, expert_library):
    """捆绑技能存在性校验：coding-style 资产不存在 → missing"""
    from backend.services.expert_service import ExpertService

    async with db_session() as s:
        await ExpertService(s).scan_experts(root=expert_library / "experts")
        await s.commit()
    async with db_session() as s:
        result = await ExpertService(s).validate_skill_bundles("code-reviewer")
    assert "coding-style" in result["missing_skills"]
