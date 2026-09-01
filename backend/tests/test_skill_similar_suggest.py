"""A-P5-3 similar AI 辅助候选验证（工单 30）

Seam（工单预确认）：SkillService.similar_suggest / similar_confirm（mock llm_chat）。
"""
import json

import pytest
from sqlalchemy import select

from backend.services.skill_service import SkillService
from platform_core.models.skill import Skill, SkillJob


async def _seed(db_session) -> None:
    async with db_session() as s:
        s.add_all([
            Skill(name="pdf-extract-a", title="A", category="document", file_path="skills/a",
                  description="PDF 抽取"),
            Skill(name="pdf-extract-b", title="B", category="document", file_path="skills/b",
                  description="PDF 抽取（另一实现）"),
            Skill(name="web-scrape", title="C", category="web", file_path="skills/c",
                  description="网页抓取"),
        ])
        await s.commit()


@pytest.mark.asyncio
async def test_similar_suggest_stores_as_suggestion_only(db_session, monkeypatch):
    import backend.services.skill_service as svc_mod

    async def _fake_llm(messages, *, usage_dim=None, budget_override=None, **kw):
        assert usage_dim == "skill_scoring"
        return json.dumps({"clusters": [["pdf-extract-a", "pdf-extract-b"]]})

    monkeypatch.setattr(svc_mod, "llm_chat", _fake_llm)
    await _seed(db_session)

    async with db_session() as s:
        result = await SkillService(s).similar_suggest()
        await s.commit()

    # 建议只进 job detail，不动 similar_to
    assert result["clusters"] == [["pdf-extract-a", "pdf-extract-b"]]
    async with db_session() as s:
        rows = {r.name: r for r in (await s.execute(select(Skill))).scalars()}
        assert all(not r.similar_to for r in rows.values())
        job = (await s.execute(select(SkillJob).order_by(SkillJob.id.desc()))).scalars().first()
        assert job.job_type == "similar_suggest"


@pytest.mark.asyncio
async def test_similar_confirm_merges_mutually(db_session):
    await _seed(db_session)
    async with db_session() as s:
        await SkillService(s).similar_confirm([["pdf-extract-a", "pdf-extract-b"]])
        await s.commit()

    async with db_session() as s:
        rows = {r.name: r for r in (await s.execute(select(Skill))).scalars()}
        assert rows["pdf-extract-a"].similar_to == ["pdf-extract-b"]
        assert rows["pdf-extract-b"].similar_to == ["pdf-extract-a"]
        assert rows["web-scrape"].similar_to in (None, [])


def test_similar_endpoints(db_client, db_engine, db_session, monkeypatch):
    import asyncio

    import backend.services.skill_service as svc_mod

    async def _fake_llm(messages, *, usage_dim=None, budget_override=None, **kw):
        return json.dumps({"clusters": [["pdf-extract-a", "pdf-extract-b"]]})

    monkeypatch.setattr(svc_mod, "llm_chat", _fake_llm)
    asyncio.run(_seed(db_session))

    resp = db_client.post("/api/v1/skills/similar-suggest")
    assert resp.status_code == 200
    assert resp.json()["data"]["clusters"] == [["pdf-extract-a", "pdf-extract-b"]]

    confirm = db_client.put(
        "/api/v1/skills/similar-confirm",
        json={"groups": [["pdf-extract-a", "pdf-extract-b"]]},
    )
    assert confirm.status_code == 200
