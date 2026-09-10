"""A-P1a-2 扫描入库服务验证（工单 09）

Seam（工单预确认）：SkillService.scan_library 公共方法（db_session + tmp_path 造目录）。
期望值为字面量（status 映射来自总方案 3.2-A-4：active→testing）。
"""
from pathlib import Path

import pytest
from sqlalchemy import select

from platform_core.models.skill import Skill, SkillJob
from backend.services.skill_service import SkillService

SKILL_MD = """---
name: demo-skill
description: 一个演示技能
---

# 演示技能

正文内容。
"""

META_YAML = """name: demo-skill
category: document-processing
industries: [software-dev]
status: active
similar_to: []
source:
  url: https://example.com/repo
  author: someone
  imported_at: 2026-08-31
  content_hash: ""
capability:
  score: null
  ai_suggested_score: null
  rubric: {}
  reviewed_by: null
  reviewed_at: null
  notes: null
"""


def _make_skill_dir(root: Path, name: str = "demo-skill", skill_md: str = SKILL_MD, meta: str = META_YAML) -> Path:
    d = root / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(skill_md)
    (d / "meta.yaml").write_text(meta)
    return d


@pytest.mark.asyncio
async def test_scan_imports_new_skill_directory(db_session, tmp_path):
    """新目录入库：name=目录名、frontmatter 提取 title/description、存量 status active→testing"""
    _make_skill_dir(tmp_path)
    async with db_session() as s:
        job = await SkillService(s).scan_library(root=tmp_path / "skills")
        await s.commit()
        row = (await s.execute(select(Skill).where(Skill.name == "demo-skill"))).scalar_one()
        assert row.title == "demo-skill" and row.description == "一个演示技能"
        assert row.category == "document-processing"
        assert row.status == "testing"  # 存量 active 映射（总方案 3.2-A-4）
        assert row.source_type == "self_built"
        assert row.sync_state == "ok"
        assert row.content_hash  # 非空哈希
        assert row.file_path.endswith("demo-skill")
    assert job["succeeded"] == 1 and job["failed"] == 0


@pytest.mark.asyncio
async def test_scan_detects_content_hash_change_preserves_governance(db_session, tmp_path):
    """SKILL.md 变更 → hash_changed；且 DB 治理字段（人工分）不被文件覆盖"""
    _make_skill_dir(tmp_path)
    async with db_session() as s:
        await SkillService(s).scan_library(root=tmp_path / "skills")
        row = (await s.execute(select(Skill).where(Skill.name == "demo-skill"))).scalar_one()
        row.score = 8.0
        row.tier = "S"
        await s.commit()

    (tmp_path / "skills" / "demo-skill" / "SKILL.md").write_text(SKILL_MD + "\n新增内容\n")
    async with db_session() as s:
        await SkillService(s).scan_library(root=tmp_path / "skills")
        await s.commit()
        row = (await s.execute(select(Skill).where(Skill.name == "demo-skill"))).scalar_one()
        assert row.sync_state == "hash_changed"
        assert float(row.score) == 8.0 and row.tier == "S"  # 治理真相源在 DB


@pytest.mark.asyncio
async def test_scan_marks_missing_directory(db_session, tmp_path):
    """DB 有行而目录被删 → missing；且不中断整批"""
    _make_skill_dir(tmp_path)
    async with db_session() as s:
        await SkillService(s).scan_library(root=tmp_path / "skills")
        await s.commit()
    import shutil

    shutil.rmtree(tmp_path / "skills" / "demo-skill")
    async with db_session() as s:
        await SkillService(s).scan_library(root=tmp_path / "skills")
        await s.commit()
        row = (await s.execute(select(Skill))).scalar_one()
        assert row.sync_state == "missing"


@pytest.mark.asyncio
async def test_scan_marks_parse_error_and_records_job(db_session, tmp_path):
    """frontmatter/meta 解析失败 → parse_error，计入失败清单，整批继续"""
    _make_skill_dir(tmp_path, name="good-skill")
    bad = tmp_path / "skills" / "bad-skill"
    bad.mkdir()
    (bad / "SKILL.md").write_text("没有 frontmatter 的正文")
    (bad / "meta.yaml").write_text("{{{ 不是合法 yaml")

    async with db_session() as s:
        job = await SkillService(s).scan_library(root=tmp_path / "skills")
        await s.commit()
        rows = {r.name: r.sync_state for r in (await s.execute(select(Skill))).scalars()}
    assert rows == {"good-skill": "ok", "bad-skill": "parse_error"}
    assert job["total"] == 2 and job["succeeded"] == 1 and job["failed"] == 1
    assert "bad-skill" in job["failed_names"]

    async with db_session() as s:
        jobs = (await s.execute(select(SkillJob))).scalars().all()
        assert jobs and jobs[-1].job_type == "scan" and jobs[-1].status == "done"
