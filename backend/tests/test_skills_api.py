"""A-P1a-3 skills 管理 API 验证（工单 10）

Seam（工单预确认）：/api/v1/skills 端点（db_client + db_session + settings 运行时重定向 LIBRARY_ROOT）。
"""
from pathlib import Path

import pytest


SKILL_MD = """---
name: alpha-skill
description: 阿尔法
---
# A
"""

META = """name: alpha-skill
category: dev-tools
industries: [software-dev]
status: stable
similar_to: []
source:
  url: ""
  author: ""
  imported_at: 2026-08-31
  content_hash: ""
capability:
  score: 8.6
  ai_suggested_score: 7.0
  rubric: {completeness: 9, doc_quality: 8}
  reviewed_by: reviewer-1
  reviewed_at: 2026-08-30
  notes: good
"""


@pytest.fixture
def skill_library(tmp_path: Path) -> Path:
    from config import settings

    original = settings.get("SKILLS.LIBRARY_ROOT")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))
    d = tmp_path / "skills" / "alpha-skill"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(SKILL_MD)
    (d / "meta.yaml").write_text(META)
    yield tmp_path
    settings.set("SKILLS.LIBRARY_ROOT", original)


async def _seed(db_session, library_root: Path) -> None:
    from backend.services.skill_service import SkillService

    async with db_session() as s:
        await SkillService(s).scan_library(root=library_root / "skills")
        await s.commit()


def test_scan_endpoint_returns_job_summary(db_client, db_engine, db_session, skill_library):
    import asyncio

    asyncio.run(_seed(db_session, skill_library))
    resp = db_client.post("/api/v1/skills/scan")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["total"] >= 1


def test_list_skills_filter_and_pagination(db_client, db_engine, db_session, skill_library):
    import asyncio

    asyncio.run(_seed(db_session, skill_library))
    resp = db_client.get("/api/v1/skills", params={"category": "dev-tools", "page": 1, "page_size": 10})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["name"] == "alpha-skill"

    # 筛选不命中
    resp = db_client.get("/api/v1/skills", params={"category": "nope"})
    assert resp.json()["data"]["total"] == 0


def test_get_skill_detail_includes_files_and_reviews(db_client, db_engine, db_session, skill_library):
    import asyncio

    asyncio.run(_seed(db_session, skill_library))
    resp = db_client.get("/api/v1/skills/alpha-skill")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["category"] == "dev-tools"
    assert data["status"] == "stable"
    assert "# A" in data["skill_md"]
    assert "category: dev-tools" in data["meta_yaml"]


def test_get_skill_detail_404(db_client, db_engine, db_session, skill_library):
    resp = db_client.get("/api/v1/skills/ghost-skill")
    assert resp.status_code == 404


def test_static_jobs_route_not_shadowed_by_name(db_client, db_engine, db_session, skill_library):
    """/skills/jobs 是静态段——若被 /{name} 吞掉会返回技能 404 而非任务列表信封"""
    resp = db_client.get("/api/v1/skills/jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "items" in body["data"]
