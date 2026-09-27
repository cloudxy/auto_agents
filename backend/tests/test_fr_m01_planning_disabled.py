"""T-01 / FR-M01：智能规划未开放 → 3s 金标句，不产方案、不入队、不抢 planning。

GWT-M01.1 提交 / M01.2 打开空态 / M01.3 只读拒绝。
可见处无 QUOTA_EXCEEDED、无裸 429、无「还没有规划」。
"""
from __future__ import annotations

import asyncio
import time

from sqlalchemy import func, select

from platform_core.models.ai_plan import AiPlan
from platform_core.models.spider_task import SpiderTask
from platform_core.models.user import User

PLAN_URL = "/api/v1/ai/plans"
COPY = "智能规划未开放"
CODE = "PLANNING_DISABLED"
READONLY_COPY = "当前账号不能开始规划"
_FORBIDDEN_CODES = {"FORBIDDEN", "QUOTA_EXCEEDED", "QUOTA_PLAN_LOCKED", "HTTP_403", "HTTP_429"}
_VISIBLE_TOKENS = ("QUOTA_EXCEEDED", "QUOTA_PLAN_LOCKED", "FORBIDDEN", "PAYMENT_NOT_CONFIGURED")


def _assert_no_inner_code(resp) -> None:
    assert resp.status_code != 429, resp.text
    body = resp.json()
    assert body["code"] not in _FORBIDDEN_CODES, body["code"]
    blob = str(body)
    for token in _VISIBLE_TOKENS:
        assert token not in blob, blob
    assert "429" not in body.get("message", "")


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


def _plan_count(db_session, tid: int) -> int:
    async def _go():
        async with db_session() as s:
            return int((await s.execute(
                select(func.count()).select_from(AiPlan).where(AiPlan.tenant_id == tid)
            )).scalar_one())

    return asyncio.run(_go())


def _task_count(db_session, tid: int) -> int:
    async def _go():
        async with db_session() as s:
            return int((await s.execute(
                select(func.count()).select_from(SpiderTask).where(SpiderTask.tenant_id == tid)
            )).scalar_one())

    return asyncio.run(_go())


def _seed_draft(db_session, tid: int) -> int:
    async def _go():
        async with db_session() as s:
            plan = AiPlan(
                target_url="https://example.com/list", status="draft", tenant_id=tid,
            )
            s.add(plan)
            await s.commit()
            await s.refresh(plan)
            return int(plan.id)

    return asyncio.run(_go())


def _plan_status(db_session, plan_id: int) -> str:
    async def _go():
        async with db_session() as s:
            return (await s.execute(
                select(AiPlan.status).where(AiPlan.id == plan_id)
            )).scalar_one()

    return asyncio.run(_go())


def _force_planning_closed(monkeypatch):
    from config import settings

    prev = settings.get("LLM.ENABLED")
    settings.set("LLM.ENABLED", False)
    monkeypatch.setattr(
        "backend.services.ai_planner_service.settings", settings, raising=False,
    )
    return prev


def test_gwt_m01_1_submit_disabled_copy_no_plan_no_enqueue(
    db_client, db_session, monkeypatch,
):
    """GWT-M01.1：未开放时提交地址 → 3s 内「智能规划未开放」；不产可入队方案；不入队。"""
    from conftest import make_tenant_owner_headers

    _force_planning_closed(monkeypatch)
    _headers, tid = make_tenant_owner_headers(db_session, slug="m01-1")
    op = _member_headers(db_session, tid, "operator", "m01-1-op")
    before_plans = _plan_count(db_session, tid)
    before_tasks = _task_count(db_session, tid)

    started = time.monotonic()
    resp = db_client.post(
        PLAN_URL, headers=op,
        json={"target_url": "https://example.com/list"},
    )
    elapsed = time.monotonic() - started
    assert elapsed <= 3
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["code"] == CODE
    assert body["message"] == COPY
    assert "还没有规划" not in body["message"]
    assert "已入队" not in body["message"]
    assert "规划已受理" not in body["message"]
    _assert_no_inner_code(resp)
    assert _plan_count(db_session, tid) == before_plans
    assert _task_count(db_session, tid) == before_tasks


def test_gwt_m01_1_trigger_does_not_claim_planning(
    db_client, db_session, monkeypatch,
):
    """GWT-M01.1：已有 draft 时触发规划不得抢成 planning 再后台失败。"""
    from conftest import make_tenant_owner_headers

    _force_planning_closed(monkeypatch)
    _headers, tid = make_tenant_owner_headers(db_session, slug="m01-1b")
    op = _member_headers(db_session, tid, "operator", "m01-1b-op")
    pid = _seed_draft(db_session, tid)

    started = time.monotonic()
    resp = db_client.post(f"{PLAN_URL}/{pid}/plan", headers=op)
    elapsed = time.monotonic() - started
    assert elapsed <= 3
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["code"] == CODE
    assert body["message"] == COPY
    _assert_no_inner_code(resp)
    assert _plan_status(db_session, pid) == "draft"
    assert _task_count(db_session, tid) == 0


def test_gwt_m01_2_open_empty_shows_disabled_copy(db_client, db_session, monkeypatch):
    """GWT-M01.2：未开放且无规划时打开列表 → 同一金标句；禁止「还没有规划」。"""
    from conftest import make_tenant_owner_headers

    _force_planning_closed(monkeypatch)
    headers, tid = make_tenant_owner_headers(db_session, slug="m01-2")
    assert _plan_count(db_session, tid) == 0
    resp = db_client.get(PLAN_URL, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["total"] == 0
    assert body["data"]["items"] == []
    assert COPY in (body.get("message") or "")
    assert "还没有规划" not in (body.get("message") or "")
    assert "加载失败" not in resp.text


def test_gwt_m01_3_viewer_submit_rejected(db_client, db_session, monkeypatch):
    """GWT-M01.3：只读提交规划 → 拒绝；不产生方案；不创建任务。"""
    from conftest import make_tenant_owner_headers

    _force_planning_closed(monkeypatch)
    _headers, tid = make_tenant_owner_headers(db_session, slug="m01-3")
    viewer = _member_headers(db_session, tid, "viewer", "m01-3-ro")
    resp = db_client.post(
        PLAN_URL, headers=viewer,
        json={"target_url": "https://example.com/list"},
    )
    _assert_no_inner_code(resp)
    assert resp.status_code in (400, 403, 422), resp.text
    assert READONLY_COPY in resp.json()["message"]
    assert _plan_count(db_session, tid) == 0
    assert _task_count(db_session, tid) == 0
