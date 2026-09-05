"""A-P2-1 评分数据链验证（工单 14）：结果校验模型 / 队列键契约 / llm_chat 维度扩展

Seam（工单预确认）：SkillScoringResult 模型、queues 常量、llm_chat 公共签名。
"""
import pytest
from pydantic import ValidationError

from platform_core.schemas.skill import SkillScoringResult

VALID_SAMPLE = {
    "completeness": 9,
    "doc_quality": 8,
    "maintenance": 7,
    "real_world_effect": 8,
    "overall": 8,
    "rationale": {"completeness": "结构完整", "doc_quality": "文档清晰",
                  "maintenance": "活跃维护", "real_world_effect": "实测有效"},
    "notes": "总体可靠",
}


class TestSkillScoringResult:
    def test_valid_sample_passes(self):
        result = SkillScoringResult.model_validate(VALID_SAMPLE)
        assert result.overall == 8 and result.notes == "总体可靠"

    def test_missing_rationale_rejected(self):
        payload = {k: v for k, v in VALID_SAMPLE.items() if k != "rationale"}
        with pytest.raises(ValidationError):
            SkillScoringResult.model_validate(payload)

    def test_out_of_range_dimension_rejected(self):
        for bad in ({"completeness": 0}, {"completeness": 11}, {"completeness": "nine"}):
            payload = {**VALID_SAMPLE, **bad}
            with pytest.raises(ValidationError):
                SkillScoringResult.model_validate(payload)


def test_skill_queue_key_contract():
    """键名契约唯一源：skill:* 键集中入 queues.py（字面量对拍）"""
    from platform_core import queues

    assert queues.SKILL_SCORE_QUEUE == "skill:score_queue"
    assert queues.SKILL_SCORER_LOCK == "skill:scorer:lock"
    assert queues.SKILL_SCAN_LOCK == "skill:scan:lock"


class _FakeResp:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"total_tokens": 10, "prompt_tokens": 6, "completion_tokens": 4},
        }


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        return _FakeResp()


async def _enable_config():
    from backend.services.llm_provider_service import LlmRuntimeConfig

    return LlmRuntimeConfig(
        base_url="https://api.test/v1", api_key="sk-test", model="test-model",
        temperature=0.2, timeout=5, max_retries=1, enabled=True,
        source="config", provider_id=None,
    )


@pytest.mark.asyncio
async def test_llm_chat_usage_dim_records_under_custom_dim(monkeypatch):
    """usage_dim 指定后计量走新维度；默认调用（不传参）行为不变"""
    import backend.services.ai_planner.llm_client as lc

    recorded = {}

    async def _fake_record(**kwargs):
        recorded.update(kwargs)

    async def _fake_month(dim, **kw):
        return 0

    monkeypatch.setattr(
        "backend.services.ai_planner_service._resolve_llm_runtime_config",
        _enable_config, raising=True,
    )
    monkeypatch.setattr(lc, "record_usage", _fake_record)
    monkeypatch.setattr(lc, "get_month_used", _fake_month)
    monkeypatch.setattr(lc.httpx, "AsyncClient", _FakeAsyncClient)

    content = await lc.llm_chat([{"role": "user", "content": "hi"}], usage_dim="skill_scoring")
    assert content == "ok"
    assert recorded["dim"] == "skill_scoring"
    assert recorded["total_tokens"] == 10


@pytest.mark.asyncio
async def test_llm_chat_budget_override_independent(monkeypatch):
    """budget_override 独立熔断：评分维度超预算被拒，不影响默认预算路径"""
    import backend.services.ai_planner.llm_client as lc

    async def _fake_month(dim, **kw):
        return 100 if dim == "skill_scoring" else 0

    async def _fake_record(**kwargs):
        return None

    monkeypatch.setattr(
        "backend.services.ai_planner_service._resolve_llm_runtime_config",
        _enable_config, raising=True,
    )
    monkeypatch.setattr(lc, "get_month_used", _fake_month)
    monkeypatch.setattr(lc, "record_usage", _fake_record)
    monkeypatch.setattr(lc.httpx, "AsyncClient", _FakeAsyncClient)

    from platform_core.exceptions import BusinessException

    with pytest.raises(BusinessException, match="预算"):
        await lc.llm_chat(
            [{"role": "user", "content": "hi"}],
            usage_dim="skill_scoring", budget_override=100,
        )
    # 默认路径不受评分维度用量影响
    content = await lc.llm_chat([{"role": "user", "content": "hi"}])
    assert content == "ok"
