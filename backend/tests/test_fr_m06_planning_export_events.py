"""T-04 / FR-M06：llm_planning_blocked / data_export_completed 超管可查；失败不挡；租户无查询面。

GWT-M06.1 规划拦住事件 / M06.2 导出成功事件 / M06.3 上报失败不挡 / M06.4 租户 404。
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.product_event import ProductEvent
from platform_core.models.spider_result import SpiderResult
from platform_core.models.spider_task import SpiderTask
from platform_core.models.user import User

PLAN_URL = "/api/v1/ai/plans"
EVENTS_URL = "/api/v1/product-events"
EXPORT_URL = "/api/v1/spiders/results/{task_id}/export"
COPY = "智能规划未开放"


def _member_headers(db_session, tid: int, tenant_role: str, username: str) -> dict:
    from backend.services.auth_service import AuthService

    role = "viewer" if tenant_role == "viewer" else (
        "admin" if tenant_role in ("owner", "admin") else "operator"
    )

    async def _go():
        async with db_session() as s:
            s.add(User(
                username=username, email=f"{username}@x.co", password_hash="x",
                role=role, tenant_id=tid, tenant_role=tenant_role, is_active=True,
            ))
            await s.commit()
            u = (await s.execute(select(User).where(User.username == username))).scalar_one()
            token = await AuthService(s).create_token({
                "id": u.id, "username": u.username, "is_admin": tenant_role in ("owner", "admin"),
                "role": role, "tenant_id": tid, "tenant_role": tenant_role,
                "is_platform_admin": False,
            })
            return token.access_token

    return {"Authorization": f"Bearer {asyncio.run(_go())}"}


def _force_planning_closed(monkeypatch):
    from config import settings

    settings.set("LLM.ENABLED", False)
    monkeypatch.setattr(
        "backend.services.ai_planner_service.settings", settings, raising=False,
    )


def _query(db_client, headers, **params):
    return db_client.get(
        EVENTS_URL, headers=headers,
        params={k: v for k, v in params.items() if v is not None},
    )


def _items(resp, name=None):
    body = resp.json()["data"]
    rows = body["items"]
    return [r for r in rows if name is None or r["event_name"] == name]


def _seed_exportable(db_session, tid: int) -> int:
    async def _go():
        async with db_session() as s:
            task = SpiderTask(
                spider_name="example", tenant_id=tid, status="completed", params="{}",
            )
            s.add(task)
            await s.flush()
            s.add(SpiderResult(
                task_id=int(task.id), spider_name="example",
                url="https://httpbin.org/get", title="row-1", tenant_id=tid,
            ))
            await s.commit()
            return int(task.id)

    return asyncio.run(_go())


def test_gwt_m06_1_planning_blocked_event_queryable(db_client, db_session, monkeypatch):
    """GWT-M06.1：M01.1 发生后超管可查 llm_planning_blocked；无该次规划出数。"""
    _force_planning_closed(monkeypatch)
    _headers, tid = make_tenant_owner_headers(db_session, slug="m06-1")
    op = _member_headers(db_session, tid, "operator", "m06-1-op")
    resp = db_client.post(
        PLAN_URL, headers=op, json={"target_url": "https://example.com/list"},
    )
    assert resp.status_code == 422, resp.text
    assert COPY in resp.json()["message"]

    admin = make_platform_admin_headers(db_session)
    rows = _items(_query(db_client, admin, event_name="llm_planning_blocked", tenant_id=tid),
                  "llm_planning_blocked")
    assert rows, resp.text
    assert rows[0]["tenant_id"] == tid
    assert (rows[0].get("props") or {}).get("reason") == "disabled"

    done = _items(_query(db_client, admin, event_name="task_completed", tenant_id=tid),
                  "task_completed")
    assert not any((r.get("props") or {}).get("result_count", 0) > 0 for r in done)


def test_gwt_m06_2_export_emits_data_export_completed(db_client, db_session):
    """GWT-M06.2：导出成功可查 data_export_completed（file_format + row_count）。"""
    headers, tid = make_tenant_owner_headers(db_session, slug="m06-2")
    task_id = _seed_exportable(db_session, tid)
    resp = db_client.get(
        EXPORT_URL.format(task_id=task_id), headers=headers, params={"format": "csv"},
    )
    assert resp.status_code == 200, resp.text
    assert b"row-1" in resp.content or "row-1" in resp.text

    admin = make_platform_admin_headers(db_session)
    rows = _items(
        _query(db_client, admin, event_name="data_export_completed", tenant_id=tid),
        "data_export_completed",
    )
    assert rows
    props = rows[0]["props"] or {}
    assert rows[0]["tenant_id"] == tid
    assert props.get("file_format") == "csv"
    assert props.get("row_count") == 1


def test_gwt_m06_3_emit_failure_does_not_block_export_or_disabled_copy(
    db_client, db_session, monkeypatch,
):
    """GWT-M06.3：上报失败不挡主路径（导出仍出文件；未开放句仍返回）。"""
    async def _boom(*_a, **_k):
        raise RuntimeError("events down")

    monkeypatch.setattr("backend.services.product_event_service._persist_event", _boom)
    _force_planning_closed(monkeypatch)

    headers, tid = make_tenant_owner_headers(db_session, slug="m06-3")
    op = _member_headers(db_session, tid, "operator", "m06-3-op")
    blocked = db_client.post(
        PLAN_URL, headers=op, json={"target_url": "https://example.com/list"},
    )
    assert blocked.status_code == 422, blocked.text
    assert COPY in blocked.json()["message"]

    task_id = _seed_exportable(db_session, tid)
    exported = db_client.get(
        EXPORT_URL.format(task_id=task_id), headers=headers, params={"format": "json"},
    )
    assert exported.status_code == 200, exported.text
    assert exported.content

    async def _count():
        async with db_session() as s:
            return list((await s.execute(select(ProductEvent))).scalars().all())

    assert asyncio.run(_count()) == []


def test_gwt_m06_4_tenant_has_no_query_surface(db_client, db_session):
    """GWT-M06.4：租户寻找产品事实查询面 → 404 同形。"""
    tenant_headers, _ = make_tenant_owner_headers(db_session, slug="m06-4")
    resp = _query(db_client, tenant_headers, event_name="llm_planning_blocked")
    assert resp.status_code == 404
    assert resp.json()["code"] == "HTTP_404"
    assert "llm_planning_blocked" not in resp.text
    assert "data_export_completed" not in resp.text
    assert "抱歉您没有权限" not in resp.text
