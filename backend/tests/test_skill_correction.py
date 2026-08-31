"""A-P1b 人工矫正与 meta 写回验证（工单 11）

Seam（工单预确认）：SkillService.correct_meta / export_meta 公共方法 + PUT 端点。
"""
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

from platform_core.models.skill import Skill, SkillJob, SkillReview
from backend.services.skill_service import SkillService

SKILL_MD = """---
name: fixme
description: 待矫正
---
# F
"""

META = """name: fixme
category: old-cat
industries: [software-dev]
status: experimental
similar_to: []
source:
  url: ""
  author: ""
  imported_at: 2026-08-31
  content_hash: ""
capability:
  score: null
  ai_suggested_score: 7.0
  rubric: {}
  reviewed_by: null
  reviewed_at: null
  notes: null
"""


async def _seed(db_session, library_root: Path) -> None:
    d = library_root / "skills" / "fixme"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(SKILL_MD)
    (d / "meta.yaml").write_text(META)
    (d / "CHANGELOG.md").write_text("# 更新记录\n")
    async with db_session() as s:
        await SkillService(s).scan_library(root=library_root / "skills")
        await s.commit()


@pytest.fixture
def library_root(tmp_path: Path) -> Path:
    """写回路径重定向到 tmp（settings 运行时写，Dynaconf 构造期快照 setenv 无效）"""
    from config import settings

    original = settings.get("SKILLS.LIBRARY_ROOT")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))
    yield tmp_path
    settings.set("SKILLS.LIBRARY_ROOT", original)


@pytest.mark.asyncio
async def test_correction_writes_db_then_meta_yaml_and_changelog(db_session, library_root):
    await _seed(db_session, library_root)
    async with db_session() as s:
        result = await SkillService(s).correct_meta(
            "fixme",
            reviewer="reviewer-1",
            payload={
                "category": "new-cat",
                "status": "stable",
                "score": 8.6,
                "rubric_human": {"completeness": 9, "doc_quality": 8, "maintenance": 8, "real_world_effect": 9},
                "review_notes": "人工复核通过",
                "similar_to": ["other-skill"],
            },
        )
        await s.commit()

        row = (await s.execute(select(Skill))).scalar_one()
        assert row.category == "new-cat" and row.status == "stable"
        assert float(row.score) == 8.6 and row.tier == "S"
        assert row.reviewed_by == "reviewer-1"
        review = (await s.execute(select(SkillReview))).scalar_one()
        assert review.reviewer_type == "human" and review.reviewer == "reviewer-1"

    meta = yaml.safe_load((library_root / "skills" / "fixme" / "meta.yaml").read_text())
    assert meta["category"] == "new-cat"
    assert meta["status"] == "stable"
    assert meta["capability"]["score"] == 8.6
    assert meta["capability"]["reviewed_by"] == "reviewer-1"
    changelog = (library_root / "skills" / "fixme" / "CHANGELOG.md").read_text()
    assert "reviewer-1" in changelog and "stable" in changelog
    assert result["written_back"] is True


@pytest.mark.asyncio
async def test_writeback_failure_keeps_db_and_records_job(db_session, library_root):
    """目录被挪走 → 写回失败：DB 保留、skill_jobs 记告警、export_meta 可补导出"""
    await _seed(db_session, library_root)
    moved = library_root / "moved-skills"
    (library_root / "skills" / "fixme").rename(moved)

    async with db_session() as s:
        result = await SkillService(s).correct_meta(
            "fixme", reviewer="reviewer-2", payload={"status": "stable", "score": 7.0}
        )
        await s.commit()
        assert result["written_back"] is False

        row = (await s.execute(select(Skill))).scalar_one()
        assert row.status == "stable" and float(row.score) == 7.0  # DB 是真相源，不回滚
        job = (await s.execute(select(SkillJob).order_by(SkillJob.id.desc()))).scalars().first()
        assert job.job_type == "export_meta" and "fixme" in (job.detail or {}).get("failed", [])

    # 目录还原后手动补导出成功
    moved.rename(library_root / "skills" / "fixme")
    async with db_session() as s:
        ok = await SkillService(s).export_meta("fixme")
        await s.commit()
    assert ok is True
    meta = yaml.safe_load((library_root / "skills" / "fixme" / "meta.yaml").read_text())
    assert meta["status"] == "stable" and meta["capability"]["score"] == 7.0


def test_put_meta_endpoint(db_client, db_engine, db_session, library_root):
    import asyncio

    asyncio.run(_seed(db_session, library_root))
    resp = db_client.put(
        "/api/v1/skills/fixme/meta",
        json={"category": "api-cat", "score": 9.0},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["category"] == "api-cat"
