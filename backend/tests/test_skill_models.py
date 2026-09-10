"""A-P1a-1 技能数据契约验证（工单 08）：三表可入库 + tier 派生边界

Seam（工单预确认）：模型行可 flush（db_session fixture）；derive_tier 纯函数。
期望值全部为字面量（tier 边界来自总方案 §5.1 派生规则原文）。
"""
import pytest

from platform_core.models.skill import Skill, SkillJob, SkillReview


@pytest.mark.asyncio
async def test_skill_models_flush_with_domain_fields(db_session):
    """三表实体满足列约束可入库，治理字段全量落位"""
    async with db_session() as s:
        skill = Skill(
            name="demo-skill",
            title="演示技能",
            description="占位",
            category="document-processing",
            industries=["software-dev"],
            status="experimental",
            source_type="self_built",
            content_hash="abc123",
            ai_suggested_score=7.2,
            rubric_ai={"completeness": 7, "doc_quality": 8},
            file_path="skills/demo-skill",
            sync_state="ok",
            raw_meta={"name": "demo-skill"},
        )
        s.add(skill)
        await s.flush()

        review = SkillReview(
            skill_id=skill.id,
            reviewer_type="ai",
            reviewer="gpt-4o-mini",
            score=7.2,
            rubric={"completeness": 7, "doc_quality": 8},
            notes="占位评语",
            content_hash="abc123",
            prompt_version="v1",
        )
        job = SkillJob(job_type="scan", status="running", total=1)
        s.add_all([review, job])
        await s.commit()
        assert skill.id and review.id and job.id


class TestDeriveTier:
    """tier = 人工分优先（缺省用 AI 分）映射：S≥8.5 / A≥7.0 / B≥5.0 / C<5.0；未评=None"""

    def test_boundaries_from_plan_rule(self):
        from backend.services.skill_service import derive_tier

        assert derive_tier(8.5, None) == "S"
        assert derive_tier(8.4, None) == "A"
        assert derive_tier(7.0, None) == "A"
        assert derive_tier(6.9, None) == "B"
        assert derive_tier(5.0, None) == "B"
        assert derive_tier(4.9, None) == "C"
        assert derive_tier(1.0, None) == "C"
        assert derive_tier(10.0, None) == "S"

    def test_human_score_takes_priority_over_ai(self):
        from backend.services.skill_service import derive_tier

        assert derive_tier(6.0, 9.5) == "B"
        assert derive_tier(None, 9.5) == "S"
        assert derive_tier(None, 7.0) == "A"
        assert derive_tier(None, 4.9) == "C"

    def test_unscored_returns_none(self):
        from backend.services.skill_service import derive_tier

        assert derive_tier(None, None) is None
