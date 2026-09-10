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


def test_similar_suggest_viewer_403(db_client, viewer_client, db_engine, db_session):
    """只读 403（SH-07：守卫 require_operator）。"""
    resp = viewer_client.post("/api/v1/skills/similar-suggest")
    assert resp.status_code == 403


def test_operator_similar_suggest_success_outbound_is_gateway_url(
    db_client, operator_client, db_engine, db_session, monkeypatch,
):
    """GWT-70.7：经办 HTTP 等到 outbound=网关 URL。禁止仅 HTTP 200 勾。"""
    import asyncio

    from config import settings

    from backend.tests.test_llm_four_actions_http import (
        GATEWAY_URL,
        _forbid_yml,
        _install_engines,
        _install_gateway,
    )

    prev = settings.get("LLM.DATA_PLANE")
    settings.set("LLM.DATA_PLANE", "litellm")
    settings.set("LITELLM.BASE_URL", GATEWAY_URL)
    settings.set("LITELLM.MASTER_KEY", "sk-virt")
    settings.set("LLM.MAX_RETRIES", 1)
    outbound: list[str] = []
    _forbid_yml(monkeypatch)
    _install_engines(monkeypatch, db_engine, db_session)
    from backend.tests.test_llm_four_actions_http import _install_llm_seams
    _install_llm_seams(monkeypatch)
    _install_gateway(
        monkeypatch, "ok", outbound,
        json.dumps({"clusters": [["pdf-extract-a", "pdf-extract-b"]]}),
    )
    asyncio.run(_seed(db_session))
    try:
        resp = operator_client.post("/api/v1/skills/similar-suggest")
        assert outbound == [f"{GATEWAY_URL}/v1/chat/completions"]
        assert "https://pub" not in outbound[0]
        assert resp.status_code == 200
        assert resp.json()["data"]["clusters"] == [["pdf-extract-a", "pdf-extract-b"]]
    finally:
        if prev is not None:
            settings.set("LLM.DATA_PLANE", prev)


def test_operator_similar_suggest_no_model_envelope_only_70_10(
    db_client, operator_client, db_engine, db_session, monkeypatch,
):
    """GWT-70.10：经办 HTTP 响应（及 Job）只「还没有平台模型」。"""
    import asyncio

    from config import settings
    from sqlalchemy import select

    from backend.services.quota_service import GATEWAY_UNREACHABLE_USER, NO_MODEL_USER
    from backend.tests.test_llm_four_actions_http import (
        GATEWAY_URL,
        _assert_only_sentence,
        _forbid_yml,
        _install_engines,
        _install_gateway,
    )

    prev = settings.get("LLM.DATA_PLANE")
    settings.set("LLM.DATA_PLANE", "litellm")
    settings.set("LITELLM.BASE_URL", GATEWAY_URL)
    settings.set("LITELLM.MASTER_KEY", "sk-virt")
    settings.set("LLM.MAX_RETRIES", 1)
    outbound: list[str] = []
    _forbid_yml(monkeypatch)
    _install_engines(monkeypatch, db_engine, db_session)
    from backend.tests.test_llm_four_actions_http import _install_llm_seams
    _install_llm_seams(monkeypatch)
    _install_gateway(monkeypatch, "no_model", outbound, "{}")
    asyncio.run(_seed(db_session))
    try:
        resp = operator_client.post("/api/v1/skills/similar-suggest")
        assert resp.status_code != 200
        body = resp.json()
        _assert_only_sentence(body["message"], NO_MODEL_USER, GATEWAY_UNREACHABLE_USER)
        assert not (resp.status_code == 200 and (body.get("data") or {}).get("clusters") == [])
        assert outbound == []
    finally:
        if prev is not None:
            settings.set("LLM.DATA_PLANE", prev)

    async def _job():
        async with db_session() as s:
            return (await s.execute(select(SkillJob).order_by(SkillJob.id.desc()))).scalars().first()

    job = asyncio.run(_job())
    assert job is not None and job.status == "failed"
    _assert_only_sentence(str(job.detail.get("reason")), NO_MODEL_USER, GATEWAY_UNREACHABLE_USER)


def test_operator_similar_suggest_unreachable_envelope_only_74_6(
    db_client, operator_client, db_engine, db_session, monkeypatch,
):
    """GWT-74.6：经办 HTTP 响应（及 Job）只「平台 LLM 网关不可达」。"""
    import asyncio

    from config import settings
    from sqlalchemy import select

    from backend.services.quota_service import GATEWAY_UNREACHABLE_USER, NO_MODEL_USER
    from backend.tests.test_llm_four_actions_http import (
        GATEWAY_URL,
        _assert_only_sentence,
        _forbid_yml,
        _install_engines,
        _install_gateway,
    )

    prev = settings.get("LLM.DATA_PLANE")
    settings.set("LLM.DATA_PLANE", "litellm")
    settings.set("LITELLM.BASE_URL", GATEWAY_URL)
    settings.set("LITELLM.MASTER_KEY", "sk-virt")
    settings.set("LLM.MAX_RETRIES", 1)
    outbound: list[str] = []
    _forbid_yml(monkeypatch)
    _install_engines(monkeypatch, db_engine, db_session)
    from backend.tests.test_llm_four_actions_http import _install_llm_seams
    _install_llm_seams(monkeypatch)
    _install_gateway(monkeypatch, "unreachable", outbound, "{}")
    asyncio.run(_seed(db_session))
    try:
        resp = operator_client.post("/api/v1/skills/similar-suggest")
        assert resp.status_code != 200
        body = resp.json()
        _assert_only_sentence(body["message"], GATEWAY_UNREACHABLE_USER, NO_MODEL_USER)
        assert not (resp.status_code == 200 and (body.get("data") or {}).get("clusters") == [])
        assert outbound == []
    finally:
        if prev is not None:
            settings.set("LLM.DATA_PLANE", prev)

    async def _job():
        async with db_session() as s:
            return (await s.execute(select(SkillJob).order_by(SkillJob.id.desc()))).scalars().first()

    job = asyncio.run(_job())
    assert job is not None and job.status == "failed"
    _assert_only_sentence(
        str(job.detail.get("reason")), GATEWAY_UNREACHABLE_USER, NO_MODEL_USER,
    )


def test_similar_endpoints(db_client, admin_client, db_engine, db_session, monkeypatch):
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
