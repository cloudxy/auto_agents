"""T-17 FR-73：本企业激活行 → 四动作 outbound=该行；网关停不得勾 74.1。

When HTTP 跟 T-16 ① /plan ② /test+_repair_flow ③ /rescore+consume_once
④ similar-suggest。禁止用第四夹具勾 73.5/73.6。
"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from cryptography.fernet import Fernet

from backend.services.llm_provider_service import LlmProviderService
from backend.services.quota_service import (
    GATEWAY_UNREACHABLE_USER,
    NO_MODEL_USER,
    PLAN_FULL_USER,
    PROVIDER_ERROR_USER,
)
from backend.tests.test_llm_four_actions_http import (
    GATEWAY_URL,
    PLAN_JSON,
    SCORE_JSON,
    _consume_once,
    _create_plan,
    _forbid_yml,
    _get_plan,
    _install_engines,
    _install_gateway,
    _install_llm_seams,
    _install_score_queue,
    _operator_headers,
    _patch_repair_first_fail,
    _patch_wait_bg,
    _seed_skill,
    _seed_test_plan,
)
from platform_core.models.llm_provider import LlmProvider
from platform_core.models.skill import Skill

OWN_BASE = "https://own.test/v1"
OWN_CHAT = f"{OWN_BASE}/chat/completions"


@pytest.fixture
def t17_plane(monkeypatch):
    from config import settings

    prev = {
        "LLM.DATA_PLANE": settings.get("LLM.DATA_PLANE"),
        "LITELLM.BASE_URL": settings.get("LITELLM.BASE_URL"),
        "LITELLM.MASTER_KEY": settings.get("LITELLM.MASTER_KEY"),
        "LLM.MAX_RETRIES": settings.get("LLM.MAX_RETRIES"),
    }
    settings.set("LLM.DATA_PLANE", "litellm")
    settings.set("LITELLM.BASE_URL", GATEWAY_URL)
    settings.set("LITELLM.MASTER_KEY", "sk-virt")
    settings.set("LLM.MAX_RETRIES", 1)

    async def _sleep(*_a, **_k):
        return None

    monkeypatch.setattr("backend.services.ai_planner.llm_client.asyncio.sleep", _sleep)

    async def _month(*_a, **_k):
        return 0

    monkeypatch.setattr("backend.services.ai_planner.llm_client.get_month_used", _month)
    yield
    for key, value in prev.items():
        if value is not None:
            settings.set(key, value)


def _install_own_row_http(monkeypatch, outbound: list, content: str, mode: str = "ok") -> None:
    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    class _Client:
        async def post(self, url, json=None, headers=None):
            outbound.append(url)
            if mode == "own_down":
                raise httpx.ConnectError("own row refused")
            return _Resp()

    async def _shared(*_a, **_k):
        return _Client()

    monkeypatch.setattr("backend.services.ai_planner_service.get_shared_client", _shared)


def _wire_byok(
    monkeypatch, db_engine, db_session, outbound: list, content: str,
    *, gw_mode: str = "ok", own_mode: str = "ok",
) -> None:
    _forbid_yml(monkeypatch)
    _install_engines(monkeypatch, db_engine, db_session)
    _install_llm_seams(monkeypatch)
    gw_out = outbound if gw_mode == "ok" else []
    _install_gateway(monkeypatch, gw_mode, gw_out, content)
    _install_own_row_http(monkeypatch, outbound, content, own_mode)
    _patch_wait_bg(monkeypatch)


def _seed_own_row(db_session, tid: int, monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENCRYPTION_KEY", Fernet.generate_key().decode())

    async def _go():
        async with db_session() as s:
            svc = LlmProviderService(s)
            s.add(LlmProvider(
                name=f"own-{tid}", provider_type="openai_compatible",
                base_url=OWN_BASE, model="own-m", tenant_id=tid,
                api_key_encrypted=svc.encrypt_api_key("sk-own"),
                is_active=True, enabled=True, max_retries=1,
            ))
            await s.commit()

    asyncio.run(_go())


def _assert_own_row_not_74_1(outbound: list) -> None:
    assert outbound == [OWN_CHAT]
    assert GATEWAY_URL not in outbound[0]
    assert "https://pub" not in outbound[0]


def _assert_not_74_1_or_quota(text: str) -> None:
    assert GATEWAY_UNREACHABLE_USER not in text
    assert PLAN_FULL_USER not in text
    assert "QUOTA_EXCEEDED" not in text


def _seed_similar(db_session, prefix: str) -> None:
    async def _go():
        async with db_session() as s:
            s.add_all([
                Skill(
                    name=f"{prefix}-a", title="A", category="document",
                    file_path=f"skills/{prefix}-a", description="PDF",
                ),
                Skill(
                    name=f"{prefix}-b", title="B", category="document",
                    file_path=f"skills/{prefix}-b", description="PDF2",
                ),
            ])
            await s.commit()

    asyncio.run(_go())


def test_post_plan_byok_outbound_own_row(
    db_client, db_engine, db_session, monkeypatch, t17_plane,
):
    """GWT-73.5：When=T-16 ① /plan；等到 outbound=本企业行侧。"""
    outbound: list[str] = []
    _wire_byok(monkeypatch, db_engine, db_session, outbound, PLAN_JSON)
    headers, tid = _operator_headers(db_session, "t17-73-5")
    _seed_own_row(db_session, tid, monkeypatch)
    pid = _create_plan(db_client, headers)
    db_client.post(f"/api/v1/ai/plans/{pid}/plan", headers=headers)
    _assert_own_row_not_74_1(outbound)


def test_post_plan_byok_gateway_down_outbound_own_row_not_74_1(
    db_client, db_engine, db_session, monkeypatch, t17_plane,
):
    """GWT-73.6：网关停；outbound=本企业行侧；不得勾 74.1。"""
    outbound: list[str] = []
    _wire_byok(
        monkeypatch, db_engine, db_session, outbound, PLAN_JSON, gw_mode="unreachable",
    )
    headers, tid = _operator_headers(db_session, "t17-73-6")
    _seed_own_row(db_session, tid, monkeypatch)
    pid = _create_plan(db_client, headers)
    db_client.post(f"/api/v1/ai/plans/{pid}/plan", headers=headers)
    _assert_own_row_not_74_1(outbound)
    data = _get_plan(db_client, headers, pid)
    _assert_not_74_1_or_quota(data.get("error_message") or "")
    assert data.get("error_message") != GATEWAY_UNREACHABLE_USER


def test_post_plan_no_own_row_follows_fr70(
    db_client, db_engine, db_session, monkeypatch, t17_plane,
):
    """GWT-73.2：无本企业激活行 → outbound=网关 URL。"""
    outbound: list[str] = []
    _wire_byok(monkeypatch, db_engine, db_session, outbound, PLAN_JSON)
    headers, _tid = _operator_headers(db_session, "t17-73-2")
    pid = _create_plan(db_client, headers)
    db_client.post(f"/api/v1/ai/plans/{pid}/plan", headers=headers)
    assert outbound == [f"{GATEWAY_URL}/v1/chat/completions"]


def test_post_test_byok_repair_flow_outbound_own_row(
    db_client, db_engine, db_session, monkeypatch, t17_plane,
):
    """GWT-73.7：When=T-16 ② /test；须 _repair_flow；outbound=本企业行侧。"""
    outbound: list[str] = []
    _wire_byok(monkeypatch, db_engine, db_session, outbound, PLAN_JSON)
    calls = _patch_repair_first_fail(monkeypatch)
    headers, tid = _operator_headers(db_session, "t17-73-7")
    _seed_own_row(db_session, tid, monkeypatch)
    pid = _seed_test_plan(db_session, tid)
    db_client.post(f"/api/v1/ai/plans/{pid}/test", headers=headers)
    assert calls["n"] >= 1
    _assert_own_row_not_74_1(outbound)


def test_post_test_byok_gateway_down_repair_flow_not_74_1(
    db_client, db_engine, db_session, monkeypatch, t17_plane,
):
    """GWT-73.10：试采 _repair_flow + 网关停；不得勾 74.1。"""
    outbound: list[str] = []
    _wire_byok(
        monkeypatch, db_engine, db_session, outbound, PLAN_JSON, gw_mode="unreachable",
    )
    calls = _patch_repair_first_fail(monkeypatch)
    headers, tid = _operator_headers(db_session, "t17-73-10")
    _seed_own_row(db_session, tid, monkeypatch)
    pid = _seed_test_plan(db_session, tid)
    db_client.post(f"/api/v1/ai/plans/{pid}/test", headers=headers)
    assert calls["n"] >= 1
    _assert_own_row_not_74_1(outbound)
    data = _get_plan(db_client, headers, pid)
    _assert_not_74_1_or_quota(data.get("error_message") or "")


def test_post_rescore_byok_consume_once_outbound_own_row(
    db_client, db_engine, db_session, monkeypatch, t17_plane,
):
    """GWT-73.8：When=T-16 ③ /rescore；须 consume_once；outbound=本企业行侧。"""
    outbound: list[str] = []
    _wire_byok(monkeypatch, db_engine, db_session, outbound, SCORE_JSON)
    _install_score_queue(monkeypatch)
    headers, tid = _operator_headers(db_session, "t17-73-8")
    _seed_own_row(db_session, tid, monkeypatch)
    name = _seed_skill(db_session, "rate-me-byok")
    resp = db_client.post(f"/api/v1/skills/{name}/rescore", headers=headers)
    result, _job = _consume_once(db_session)
    assert result.get("status") == "scored"
    _assert_own_row_not_74_1(outbound)
    assert resp.status_code == 200


def test_post_rescore_byok_gateway_down_consume_once_not_74_1(
    db_client, db_engine, db_session, monkeypatch, t17_plane,
):
    """GWT-73.11：评分 consume_once + 网关停；不得勾 74.1。"""
    outbound: list[str] = []
    _wire_byok(
        monkeypatch, db_engine, db_session, outbound, SCORE_JSON, gw_mode="unreachable",
    )
    _install_score_queue(monkeypatch)
    headers, tid = _operator_headers(db_session, "t17-73-11")
    _seed_own_row(db_session, tid, monkeypatch)
    name = _seed_skill(db_session, "rate-me-byok-down")
    db_client.post(f"/api/v1/skills/{name}/rescore", headers=headers)
    result, job = _consume_once(db_session)
    assert result.get("status") == "scored"
    _assert_own_row_not_74_1(outbound)
    err = (result.get("error") or "") + str((job.detail or {}).get("reason") if job else "")
    _assert_not_74_1_or_quota(err)


def test_similar_suggest_byok_outbound_own_row(
    db_client, db_engine, db_session, monkeypatch, t17_plane,
):
    """GWT-73.9：经办 HTTP similar-suggest；outbound=本企业行侧。"""
    outbound: list[str] = []
    clusters = json.dumps({"clusters": [["t17-sim-a", "t17-sim-b"]]})
    _wire_byok(monkeypatch, db_engine, db_session, outbound, clusters)
    headers, tid = _operator_headers(db_session, "t17-73-9")
    _seed_own_row(db_session, tid, monkeypatch)
    _seed_similar(db_session, "t17-sim")
    resp = db_client.post("/api/v1/skills/similar-suggest", headers=headers)
    _assert_own_row_not_74_1(outbound)
    assert resp.status_code == 200
    assert resp.json()["data"]["clusters"] == [["t17-sim-a", "t17-sim-b"]]


def test_similar_suggest_byok_gateway_down_not_74_1(
    db_client, db_engine, db_session, monkeypatch, t17_plane,
):
    """GWT-73.12：第四夹具 + 网关停；不得勾 74.1。"""
    outbound: list[str] = []
    clusters = json.dumps({"clusters": [["t17-simd-a", "t17-simd-b"]]})
    _wire_byok(
        monkeypatch, db_engine, db_session, outbound, clusters, gw_mode="unreachable",
    )
    headers, tid = _operator_headers(db_session, "t17-73-12")
    _seed_own_row(db_session, tid, monkeypatch)
    _seed_similar(db_session, "t17-simd")
    resp = db_client.post("/api/v1/skills/similar-suggest", headers=headers)
    _assert_own_row_not_74_1(outbound)
    assert resp.status_code == 200
    body = resp.json()
    _assert_not_74_1_or_quota(body.get("message") or "")
    assert GATEWAY_UNREACHABLE_USER not in str(body)
    assert PROVIDER_ERROR_USER not in str(body)
    assert NO_MODEL_USER not in str(body)
