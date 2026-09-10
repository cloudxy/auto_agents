"""T-27 FR-36：超管/系统引用列表忽略 listing；黑名单跳过+审计。非执行引擎。"""
import asyncio

from sqlalchemy import select

from backend.services.power_market import (
    STORE_NOT_FOUND_COPY,
    STORE_NOT_FOUND_HOME,
    STORE_NOT_FOUND_HTML,
)
from backend.tests.fr33_support import utcnow
from backend.tests.t25_support import bind_actor, seed_tenant
from backend.tests.t27_support import refs_url, seed_agent_collection, seed_gift_install
from platform_core.models.operation_log import OperationLog

_SKIP = "market.ref.skip"
_EXEC = ("执行引擎", "召唤", "runtime execute", "/execute")


def _item_names(payload: dict) -> set[str]:
    return {i["name"] for i in payload.get("items") or []}


def _skip_logs(db_session) -> list[OperationLog]:
    async def _go():
        async with db_session() as s:
            rows = (await s.execute(
                select(OperationLog).where(OperationLog.action == _SKIP)
            )).scalars().all()
            return list(rows)

    return asyncio.run(_go())


def _assert_not_execution(text: str) -> None:
    for token in _EXEC:
        assert token not in text


def test_gwt_36_1_unlisted_ref_still_in_list(
    platform_admin_client, db_client, db_engine, db_session,
):
    """When=超管打开智能体引用列表（非租户执行面）。未上架非黑名单仍在。"""
    tid = seed_tenant(db_session, "t27-gift")
    seed_agent_collection(db_session, agent="g361-agent", children=[
        {"name": "g361-unlisted", "listing_state": "unlisted", "role": "uses_skill"},
        {"name": "g361-listed", "listing_state": "listed", "role": "uses_skill"},
        {"name": "g361-origin", "listing_state": "unlisted", "role": "bundled_skill"},
        {
            "name": "g361-nolic", "listing_state": "unlisted",
            "license": "NOASSERTION", "role": "uses_skill",
        },
    ])
    seed_gift_install(db_session, tenant_id=tid, name="g361-gift")
    resp = platform_admin_client.get(refs_url("agent", "g361-agent"))
    assert resp.status_code == 200, resp.text
    _assert_not_execution(resp.text)
    names = _item_names(resp.json()["data"])
    assert "g361-unlisted" in names
    assert "g361-listed" in names
    assert "g361-origin" in names
    assert "g361-nolic" in names
    assert "g361-gift" not in names
    unlisted = next(
        i for i in resp.json()["data"]["items"] if i["name"] == "g361-unlisted"
    )
    assert unlisted["listing_state"] == "unlisted"


def test_gwt_36_2_blacklist_skipped_with_audit(
    platform_admin_client, db_client, db_engine, db_session,
):
    """When=超管打开引用列表。黑名单/软删跳过并有审计；商店两边都不出现。"""
    seed_agent_collection(db_session, agent="g362-agent", children=[
        {"name": "g362-ok", "listing_state": "listed", "role": "uses_skill"},
        {
            "name": "g362-black", "status": "blacklist",
            "listing_state": "listed", "role": "uses_skill",
        },
        {
            "name": "g362-gone", "deleted_at": utcnow(),
            "listing_state": "listed", "role": "uses_skill",
        },
    ])
    resp = platform_admin_client.get(refs_url("agent", "g362-agent"))
    assert resp.status_code == 200, resp.text
    _assert_not_execution(resp.text)
    names = _item_names(resp.json()["data"])
    assert names == {"g362-ok"}
    logs = _skip_logs(db_session)
    blob = " ".join(f"{row.target} {row.detail or ''}" for row in logs)
    assert "g362-black" in blob and "blacklist" in blob
    assert "g362-gone" in blob and "deleted" in blob
    skills = {
        i["name"] for i in db_client.get("/api/v1/public/skills").json()["data"]["items"]
    }
    caps = {
        i["name"]
        for i in db_client.get("/api/v1/public/capabilities").json()["data"]["items"]
    }
    assert "g362-black" not in skills and "g362-black" not in caps
    assert "g362-gone" not in skills and "g362-gone" not in caps
    black = db_client.get("/api/v1/public/skills/g362-black")
    gone = db_client.get("/api/v1/public/skills/g362-gone")
    html = STORE_NOT_FOUND_HTML.encode("utf-8")
    assert black.content == gone.content == html


def test_gwt_36_3_tenant_unlisted_store_html_404(
    app, platform_admin_client, db_client, db_engine, db_session,
):
    """租户打开未上架商店页走 GWT-32.3 同句；解析列表不是商店泄漏。"""
    seed_agent_collection(db_session, agent="g363-agent", children=[
        {"name": "g363-unlisted", "listing_state": "unlisted", "role": "uses_skill"},
    ])
    admin = platform_admin_client.get(refs_url("agent", "g363-agent"))
    assert admin.status_code == 200, admin.text
    assert "g363-unlisted" in _item_names(admin.json()["data"])
    ghost = db_client.get("/api/v1/public/skills/never-existed-g363")
    unlisted = db_client.get("/api/v1/public/skills/g363-unlisted")
    html = STORE_NOT_FOUND_HTML.encode("utf-8")
    assert ghost.status_code == unlisted.status_code == 404
    assert ghost.content == unlisted.content == html
    assert STORE_NOT_FOUND_COPY in unlisted.text
    assert STORE_NOT_FOUND_HOME in unlisted.text
    assert "已下架" not in unlisted.text
    includes = db_client.get(
        "/api/v1/public/capabilities/agent/g363-agent",
    ).json()["data"].get("includes") or []
    assert "g363-unlisted" not in {i["name"] for i in includes}
    tid = seed_tenant(db_session, "t27-op")
    bind_actor(app, role="operator", tenant_id=tid, tenant_role="operator")
    denied = db_client.get(refs_url("agent", "g363-agent"))
    assert denied.status_code == 403
