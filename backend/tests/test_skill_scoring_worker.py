"""A-P2-2 评分 worker 验证（工单 15）

Seam（工单预确认）：SkillScoringService.enqueue_rescore / consume_once / score_skill
（db_session + 队列桩 + monkeypatch llm_chat）。AI 永不写人工权威分。
"""
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from platform_core.models.skill import Skill, SkillJob, SkillReview
from backend.services.skill_service import SkillService

SKILL_MD = """---
name: rate-me
description: 待评分
---
# R
"""

VALID = {
    "completeness": 8, "doc_quality": 7, "maintenance": 6, "real_world_effect": 7,
    "overall": 7,
    "rationale": {"completeness": "全", "doc_quality": "清", "maintenance": "活", "real_world_effect": "效"},
    "notes": "总体可用",
}


class FakeQueueRedis:
    """评分队列桩：lpush/rpop/lrange"""

    def __init__(self):
        self.items: list[str] = []

    async def lpush(self, key, value):
        self.items.insert(0, value)
        return len(self.items)

    async def rpop(self, key):
        return self.items.pop() if self.items else None

    async def lrange(self, key, start, end):
        return list(self.items)


@pytest.fixture
def queue_redis(monkeypatch):
    fake = FakeQueueRedis()
    async def _fake_get_async_redis(key: str = "DEFAULT"):
        return fake
    # scoring 模块顶层绑定 + 源模块（skill_service 懒导入取的是源模块属性）
    monkeypatch.setattr("backend.services.skill_scoring_service.get_async_redis", _fake_get_async_redis)
    monkeypatch.setattr("platform_core.redis_async.get_async_redis", _fake_get_async_redis)
    return fake


@pytest.fixture
def library_root(tmp_path):
    from config import settings

    original = settings.get("SKILLS.LIBRARY_ROOT")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))
    yield tmp_path
    settings.set("SKILLS.LIBRARY_ROOT", original)


@pytest.fixture
def seeded(db_session, library_root):
    d = Path(library_root) / "skills" / "rate-me"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(SKILL_MD)
    (d / "meta.yaml").write_text("name: rate-me\nstatus: experimental\n")

    async def _go():
        async with db_session() as s:
            await SkillService(s).scan_library(root=Path(library_root) / "skills")
            await s.commit()

    import asyncio

    asyncio.run(_go())
    return "rate-me"


@pytest.mark.asyncio
async def test_consume_once_scores_and_records_review(db_session, queue_redis, seeded, monkeypatch):
    import backend.services.skill_scoring_service as svc

    calls = {}

    async def _fake_llm_chat(messages, *, usage_dim=None, budget_override=None):
        calls["usage_dim"] = usage_dim
        calls["budget_override"] = budget_override
        return json.dumps(VALID, ensure_ascii=False)

    monkeypatch.setattr(svc, "llm_chat", _fake_llm_chat)
    await svc.SkillScoringService.enqueue_rescore(seeded)

    async with db_session() as s:
        result = await svc.SkillScoringService(s).consume_once()
        await s.commit()

        row = (await s.execute(select(Skill))).scalar_one()
        review = (await s.execute(select(SkillReview))).scalar_one()
    assert result["status"] == "scored"
    assert row.ai_suggested_score == 7.0 and row.rubric_ai["completeness"] == 8
    assert row.score is None and row.rubric_human is None  # AI 永不写人工权威分
    assert review.reviewer_type == "ai" and review.prompt_version == "v1"
    assert review.content_hash == row.content_hash
    assert calls["usage_dim"] == "skill_scoring"


@pytest.mark.asyncio
async def test_invalid_json_retries_once_then_records_failure(db_session, queue_redis, seeded, monkeypatch):
    import backend.services.skill_scoring_service as svc

    async def _always_bad(messages, *, usage_dim=None, budget_override=None):
        return "这不是 JSON"

    monkeypatch.setattr(svc, "llm_chat", _always_bad)
    await svc.SkillScoringService.enqueue_rescore(seeded)

    async with db_session() as s:
        result = await svc.SkillScoringService(s).consume_once()
        await s.commit()
        jobs = (await s.execute(select(SkillJob))).scalars().all()
        reviews = (await s.execute(select(SkillReview))).scalars().all()
    assert result["status"] == "failed"
    assert result["attempts"] == 2  # 重试 1 次后仍失败
    assert any(j.job_type == "score_batch" and j.failed == 1 for j in jobs)
    assert reviews == []


@pytest.mark.asyncio
async def test_invalid_then_valid_succeeds_on_retry(db_session, queue_redis, seeded, monkeypatch):
    import backend.services.skill_scoring_service as svc

    outputs = iter(["```json\n{broken", json.dumps(VALID)])

    async def _flaky(messages, *, usage_dim=None, budget_override=None):
        return next(outputs)

    monkeypatch.setattr(svc, "llm_chat", _flaky)
    await svc.SkillScoringService.enqueue_rescore(seeded)

    async with db_session() as s:
        result = await svc.SkillScoringService(s).consume_once()
        await s.commit()
    assert result["status"] == "scored" and result["attempts"] == 2


def test_rescore_endpoint_pushes_queue(db_client, db_engine, db_session, queue_redis, seeded):
    resp = db_client.post("/api/v1/skills/rate-me/rescore")
    assert resp.status_code == 200
    assert "rate-me" in queue_redis.items
