"""B-M2-1 多模型数据模型与 API 验证（工单 22）

Seam（工单预确认）：GET/PUT /llm/providers/{id}/models 端点 + 服务方法。
"""
from sqlalchemy import func, select

from platform_core.models.llm_provider import LlmProvider
from platform_core.models.llm_provider_model import LlmProviderModel


def _create_provider(db_client, name: str) -> int:
    resp = db_client.post(
        "/api/v1/llm/providers",
        json={"name": name, "provider_type": "anthropic",
              "base_url": "https://api.anthropic.com", "model": "claude-sonnet-4-6"},
    )
    assert resp.status_code == 200
    return resp.json()["data"]["id"]


def test_put_models_full_replace_and_default_sync(db_client, db_engine, db_session):
    provider_id = _create_provider(db_client, "multi-model")

    first = db_client.put(
        f"/api/v1/llm/providers/{provider_id}/models",
        json={"models": [
            {"model_id": "claude-sonnet-4-6", "model_tier": "strong", "priority": 10, "is_default": True},
            {"model_id": "claude-haiku-4-5", "model_tier": "basic", "priority": 50},
        ]},
    )
    assert first.status_code == 200

    listing = db_client.get(f"/api/v1/llm/providers/{provider_id}/models").json()["data"]
    assert {m["model_id"] for m in listing} == {"claude-sonnet-4-6", "claude-haiku-4-5"}

    # 默认模型变更 → 父行 model 冗余列同事务刷新
    second = db_client.put(
        f"/api/v1/llm/providers/{provider_id}/models",
        json={"models": [
            {"model_id": "claude-sonnet-4-6", "model_tier": "strong", "priority": 10},
            {"model_id": "claude-haiku-4-5", "model_tier": "basic", "priority": 50, "is_default": True},
            {"model_id": "claude-opus-4", "model_tier": "strong", "priority": 5},
        ]},
    )
    assert second.status_code == 200

    import asyncio

    async def _check():
        async with db_session() as s:
            parent = (await s.execute(select(LlmProvider).where(LlmProvider.id == provider_id))).scalar_one()
            rows = (await s.execute(select(LlmProviderModel))).scalars().all()
            return parent, rows

    parent, rows = asyncio.run(_check())
    assert parent.model == "claude-haiku-4-5"  # 冗余快照随默认变更
    assert {r.model_id for r in rows} == {"claude-sonnet-4-6", "claude-haiku-4-5", "claude-opus-4"}  # 全量替换


def test_multiple_defaults_returns_422(db_client, db_engine, db_session):
    provider_id = _create_provider(db_client, "two-defaults")
    resp = db_client.put(
        f"/api/v1/llm/providers/{provider_id}/models",
        json={"models": [
            {"model_id": "a", "is_default": True},
            {"model_id": "b", "is_default": True},
        ]},
    )
    assert resp.status_code == 422


def test_delete_provider_cascades_models(db_client, db_engine, db_session):
    provider_id = _create_provider(db_client, "cascade-me")
    put = db_client.put(
        f"/api/v1/llm/providers/{provider_id}/models",
        json={"models": [{"model_id": "m1", "is_default": True}, {"model_id": "m2"}]},
    )
    assert put.status_code == 200

    dele = db_client.delete(f"/api/v1/llm/providers/{provider_id}")
    assert dele.status_code == 200

    import asyncio

    async def _count():
        async with db_session() as s:
            return (await s.execute(select(func.count()).select_from(LlmProviderModel))).scalar_one()

    assert asyncio.run(_count()) == 0  # 级联清空
