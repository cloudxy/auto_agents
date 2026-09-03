"""B-M2-2 fetch diff + 逐模型健康测试验证（工单 23）

Seam（工单预确认）：端点 + LlmProviderService.fetch_models_diff/test_model。
"""

from sqlalchemy import select

import backend.services.llm_protocol.adapters as adapters_mod
import backend.services.llm_provider_service as svc_mod
from platform_core.models.llm_provider_model import LlmProviderModel
from backend.services.llm_protocol import ProtocolError


def _setup(db_client, name="fetch-me"):
    pid = db_client.post(
        "/api/v1/llm/providers",
        json={"name": name, "provider_type": "openai_compatible",
              "base_url": "https://api.test/v1", "model": "m-b"},
    ).json()["data"]["id"]
    put = db_client.put(
        f"/api/v1/llm/providers/{pid}/models",
        json={"models": [
            {"model_id": "m-a", "is_default": False},
            {"model_id": "m-b", "is_default": True},
        ]},
    )
    assert put.status_code == 200
    return pid


def _patch_execute(monkeypatch, body=None, error=None):
    async def _fake(client, method, url, headers, json_payload=None):
        if error is not None:
            raise error
        return body if body is not None else {}
    monkeypatch.setattr(adapters_mod, "execute_json", _fake)
    monkeypatch.setattr(svc_mod, "execute_json", _fake)


def test_fetch_diff_three_way(db_client, db_engine, db_session, monkeypatch):
    pid = _setup(db_client)
    _patch_execute(monkeypatch, body={"data": [
        {"id": "m-b", "owned_by": "openai"}, {"id": "m-c", "owned_by": "openai"},
    ]})

    resp = db_client.post(f"/api/v1/llm/providers/{pid}/models/fetch")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["new"] == ["m-c"]
    assert data["existing"] == ["m-b"]
    assert data["vanished"] == ["m-a"]

    # fetch 不直写：本地子表仍是 m-a/m-b
    import asyncio

    async def _rows():
        async with db_session() as s:
            return sorted(r.model_id for r in (
                await s.execute(select(LlmProviderModel))
            ).scalars())

    assert asyncio.run(_rows()) == ["m-a", "m-b"]


def test_model_test_writes_health_states(db_client, db_engine, db_session, monkeypatch):
    pid = _setup(db_client, name="health-me")

    # 200 → healthy + 延迟 + 时间
    _patch_execute(monkeypatch, body={"choices": [{"message": {"content": "pong"}}]})
    ok = db_client.post(f"/api/v1/llm/providers/{pid}/models/m-a/test").json()["data"]
    assert ok["ok"] is True and ok["latency_ms"] >= 0

    import asyncio

    async def _status(model_id):
        async with db_session() as s:
            row = (await s.execute(
                select(LlmProviderModel).where(
                    LlmProviderModel.provider_id == pid,
                    LlmProviderModel.model_id == model_id,
                )
            )).scalar_one()
            return row.health_status, row.last_latency_ms, row.last_checked_at

    status, latency, checked = asyncio.run(_status("m-a"))
    assert status == "healthy" and latency is not None and checked is not None

    # 401 → down
    _patch_execute(monkeypatch, error=ProtocolError("HTTP 401 Unauthorized"))
    db_client.post(f"/api/v1/llm/providers/{pid}/models/m-a/test")
    assert asyncio.run(_status("m-a"))[0] == "down"

    # 网络/超时 → degraded
    _patch_execute(monkeypatch, error=ProtocolError("网络错误: read timeout"))
    db_client.post(f"/api/v1/llm/providers/{pid}/models/m-a/test")
    assert asyncio.run(_status("m-a"))[0] == "degraded"


def test_model_test_unsaved_model_one_shot(db_client, db_engine, monkeypatch):
    """导入新增的未落库模型：测试不 404，一次性结果即回（保存后才持久化）"""
    import backend.services.llm_provider_service as svc_mod
    from backend.services.llm_protocol import ProtocolError

    provider_id = _setup(db_client)

    async def _ok(client, method, url, headers, json_payload=None):
        return {"choices": [{"message": {"content": "pong"}}]}

    async def _unauth(client, method, url, headers, json_payload=None):
        raise ProtocolError("HTTP 401 Unauthorized")

    # 未保存模型 → 一次性 healthy
    monkeypatch.setattr(svc_mod, "execute_json", _ok)
    resp = db_client.post(f"/api/v1/llm/providers/{provider_id}/models/ghost-model/test")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["ok"] is True and data["model"] == "ghost-model" and data["health_status"] == "healthy"

    # 一次性 down（401 语义）也不落库、不 404
    monkeypatch.setattr(svc_mod, "execute_json", _unauth)
    resp2 = db_client.post(f"/api/v1/llm/providers/{provider_id}/models/ghost-model/test")
    assert resp2.status_code == 200
    assert resp2.json()["data"]["health_status"] == "down"
