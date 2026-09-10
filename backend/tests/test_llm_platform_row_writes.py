"""T-04 GWT-06.5 / 06.6：本企业供应商可保存；平台级行租户负责人拒绝且行不变。

禁止把 operator 403 写成 /llm 写面完成态（T-17 拥有经办写与 test）。
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from conftest import make_tenant_owner_headers
from backend.tests.test_llm_four_actions_http import _operator_headers
from platform_core.models.llm_provider import LlmProvider
from platform_core.models.operation_log import OperationLog


def _body(name: str) -> dict:
    return {
        "name": name,
        "provider_type": "openai_compatible",
        "base_url": "https://llm.example.test/v1",
        "model": "m-own",
    }


def test_owner_saves_own_tenant_provider_row(db_client, db_session):
    """GWT-06.5：企业负责人保存本企业行 → 200；行归属本租户"""
    headers, tenant_id = make_tenant_owner_headers(db_session, slug="byok-own")
    resp = db_client.post("/api/v1/llm/providers", json=_body("own-key"), headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == "CREATED"
    pid = resp.json()["data"]["id"]

    async def _row():
        async with db_session() as s:
            return (await s.execute(
                select(LlmProvider).where(LlmProvider.id == pid)
            )).scalar_one()

    row = asyncio.run(_row())
    assert row.name == "own-key"
    assert row.tenant_id == tenant_id


def test_owner_activate_platform_provider_rejected_row_unchanged(db_client, db_session):
    """GWT-06.6：企业负责人激活平台级供应商 → 拒绝且平台行不变"""
    async def _seed():
        async with db_session() as s:
            s.add(LlmProvider(
                name="platform-pub", provider_type="openai_compatible",
                base_url="https://pub.example.test/v1", model="m-pub",
                tenant_id=None, is_active=False, enabled=True,
            ))
            await s.commit()
            return (await s.execute(
                select(LlmProvider).where(LlmProvider.name == "platform-pub")
            )).scalar_one().id

    pid = asyncio.run(_seed())
    headers, _ = make_tenant_owner_headers(db_session, slug="byok-act")
    resp = db_client.put(f"/api/v1/llm/providers/{pid}/activate", headers=headers)
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "FORBIDDEN"

    async def _check():
        async with db_session() as s:
            row = (await s.execute(
                select(LlmProvider).where(LlmProvider.id == pid)
            )).scalar_one()
            logs = list((await s.execute(
                select(OperationLog).where(OperationLog.action == "authz.denied")
            )).scalars().all())
            return row.is_active, logs

    is_active, logs = asyncio.run(_check())
    assert is_active is False
    assert logs
    assert f"llm_provider#{pid}" in logs[0].target


def test_owner_update_platform_provider_rejected_row_unchanged(db_client, db_session):
    """GWT-06.6：企业负责人改平台级供应商 → 拒绝且平台行不变"""
    async def _seed():
        async with db_session() as s:
            s.add(LlmProvider(
                name="platform-edit", provider_type="openai_compatible",
                base_url="https://pub.example.test/v1", model="m-old",
                tenant_id=None, is_active=False, enabled=True,
            ))
            await s.commit()
            return (await s.execute(
                select(LlmProvider).where(LlmProvider.name == "platform-edit")
            )).scalar_one().id

    pid = asyncio.run(_seed())
    headers, _ = make_tenant_owner_headers(db_session, slug="byok-upd")
    resp = db_client.put(
        f"/api/v1/llm/providers/{pid}",
        json={"model": "m-hacked"},
        headers=headers,
    )
    assert resp.status_code == 403, resp.text

    async def _model():
        async with db_session() as s:
            return (await s.execute(
                select(LlmProvider.model).where(LlmProvider.id == pid)
            )).scalar_one()

    assert asyncio.run(_model()) == "m-old"


def test_operator_saves_own_tenant_provider_row(db_client, db_session):
    """GWT-73.1 / 06.5：经办保存本企业行 → 200；行归属本租户"""
    headers, tenant_id = _operator_headers(db_session, "byok-op-own")
    resp = db_client.post("/api/v1/llm/providers", json=_body("op-key"), headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == "CREATED"
    pid = resp.json()["data"]["id"]

    async def _row():
        async with db_session() as s:
            return (await s.execute(
                select(LlmProvider).where(LlmProvider.id == pid)
            )).scalar_one()

    row = asyncio.run(_row())
    assert row.name == "op-key"
    assert row.tenant_id == tenant_id


def test_operator_activate_platform_provider_rejected_row_unchanged(db_client, db_session):
    """GWT-73.3 / 06.6：经办激活平台级行 → 拒绝且平台行不变"""
    async def _seed():
        async with db_session() as s:
            s.add(LlmProvider(
                name="platform-op", provider_type="openai_compatible",
                base_url="https://pub.example.test/v1", model="m-pub",
                tenant_id=None, is_active=False, enabled=True,
            ))
            await s.commit()
            return (await s.execute(
                select(LlmProvider).where(LlmProvider.name == "platform-op")
            )).scalar_one().id

    pid = asyncio.run(_seed())
    headers, _ = _operator_headers(db_session, "byok-op-act")
    resp = db_client.put(f"/api/v1/llm/providers/{pid}/activate", headers=headers)
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "FORBIDDEN"

    async def _check():
        async with db_session() as s:
            return (await s.execute(
                select(LlmProvider).where(LlmProvider.id == pid)
            )).scalar_one().is_active

    assert asyncio.run(_check()) is False


def test_operator_test_platform_provider_rejected(db_client, db_session):
    """GWT-73.3：经办测平台级行 → 403，不打该行地址当本企业测试连接"""
    async def _seed():
        async with db_session() as s:
            s.add(LlmProvider(
                name="platform-test", provider_type="openai_compatible",
                base_url="https://pub.example.test/v1", model="m-pub",
                tenant_id=None, is_active=False, enabled=True,
            ))
            await s.commit()
            return (await s.execute(
                select(LlmProvider).where(LlmProvider.name == "platform-test")
            )).scalar_one().id

    pid = asyncio.run(_seed())
    headers, _ = _operator_headers(db_session, "byok-op-test")
    resp = db_client.post(f"/api/v1/llm/providers/{pid}/test", headers=headers)
    assert resp.status_code == 403, resp.text
