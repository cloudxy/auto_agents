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
        # ADR-0007 D2：返回名称快照（dict），不再回传 ORM 实例
        assert team == {"name": "review-team", "created": True}

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


# ---------------------------------------------------------------------------
# T-37（FR-101）：成员域扩 expert∪agent（GWT-101.1..101.4 后端域）
# ---------------------------------------------------------------------------


async def _seed_agent_asset(db_session, name: str) -> None:
    """直插智能体目录行（成员域 (type, name) 引用校验用）"""
    from platform_core.models.capability import CapabilityAsset

    async with db_session() as s:
        s.add(CapabilityAsset(
            asset_type="agent", name=name, title=f"智能体 {name}",
            category="agent", status="stable", sync_state="ok",
        ))
        await s.commit()


async def _scan_experts(db_session, expert_library) -> None:
    from backend.services.expert_service import ExpertService

    async with db_session() as s:
        await ExpertService(s).scan_experts(root=expert_library / "experts")
        await s.commit()


@pytest.mark.asyncio
async def test_team_mixed_members_expert_union_agent(db_session, expert_library):
    """GWT-101.1/101.2：agent 可作成员；混合成员详情/导出各自标注类型"""
    from backend.services.expert_service import TeamService

    await _scan_experts(db_session, expert_library)
    await _seed_agent_asset(db_session, "researcher")

    async with db_session() as s:
        team = await TeamService(s).upsert_team(
            "mixed-team", leader="code-reviewer",
            members=[{"type": "expert", "name": "code-reviewer"},
                     {"type": "agent", "name": "researcher"}])
        detail = await TeamService(s).get_team_detail("mixed-team")
        exported = await TeamService(s).export_team_md("mixed-team")

    assert team == {"name": "mixed-team", "created": True}
    assert {"type": "expert", "name": "code-reviewer"} in detail["members"]
    assert {"type": "agent", "name": "researcher"} in detail["members"]
    assert "researcher（智能体）" in exported
    assert "code-reviewer（专家）" in exported


@pytest.mark.asyncio
async def test_team_expert_only_when_no_agent_assets(db_session, expert_library):
    """GWT-101.4：目录 agent 资产为 0 → 仍可仅用专家完成组建（dict/str 两形态）"""
    from backend.services.expert_service import TeamService

    await _scan_experts(db_session, expert_library)

    async with db_session() as s:
        await TeamService(s).upsert_team(
            "expert-only", leader="code-reviewer",
            members=[{"type": "expert", "name": "code-reviewer"}])
        detail = await TeamService(s).get_team_detail("expert-only")
    assert detail["members"] == [{"type": "expert", "name": "code-reviewer"}]

    # 旧字符串形态（兼容既有调用）：按专家校验，原样存取
    async with db_session() as s:
        await TeamService(s).upsert_team(
            "legacy-shape", leader="code-reviewer", members=["code-reviewer"])
        legacy = await TeamService(s).get_team_detail("legacy-shape")
        legacy_md = await TeamService(s).export_team_md("legacy-shape")
    assert legacy["members"] == ["code-reviewer"]
    assert "（专家）" not in legacy_md.split("**成员**：")[-1].splitlines()[0]


@pytest.mark.asyncio
async def test_team_leader_must_be_expert_not_agent(db_session, expert_library):
    """GWT-101.3（后端半）：组长可选域不扩——智能体当团长 → 422 中文句"""
    from platform_core.exceptions import ValidationException

    from backend.services.expert_service import TeamService

    await _scan_experts(db_session, expert_library)
    await _seed_agent_asset(db_session, "researcher")

    async with db_session() as s:
        with pytest.raises(ValidationException, match="团长必须从专家中选择"):
            await TeamService(s).upsert_team(
                "bad-leader", leader="researcher",
                members=[{"type": "expert", "name": "code-reviewer"}])


@pytest.mark.asyncio
async def test_team_duplicate_member_rejected(db_session, expert_library):
    """同 (type, name) 重复成员 → 422 中文句（去重）"""
    from platform_core.exceptions import ValidationException

    from backend.services.expert_service import TeamService

    await _scan_experts(db_session, expert_library)
    await _seed_agent_asset(db_session, "researcher")

    async with db_session() as s:
        with pytest.raises(ValidationException, match="重复"):
            await TeamService(s).upsert_team(
                "dup-team", leader="code-reviewer",
                members=[{"type": "agent", "name": "researcher"},
                         {"type": "agent", "name": "researcher"}])


@pytest.mark.asyncio
async def test_team_agent_dangling_and_bad_type(db_session, expert_library):
    """智能体悬空引用 → 422；非法成员类型 → 422（均为中文句）"""
    from platform_core.exceptions import ValidationException

    from backend.services.expert_service import TeamService

    await _scan_experts(db_session, expert_library)

    async with db_session() as s:
        with pytest.raises(ValidationException, match="智能体引用不存在"):
            await TeamService(s).upsert_team(
                "dangling-agent", leader="code-reviewer",
                members=[{"type": "agent", "name": "ghost-agent"}])
    async with db_session() as s:
        with pytest.raises(ValidationException, match="成员类型非法"):
            await TeamService(s).upsert_team(
                "bad-type", leader="code-reviewer",
                members=[{"type": "skill", "name": "some-skill"}])
