"""T-12 / FR-M20 FR-M26 [SEC-2]：出站拉数只命中出站签发行。"""
from __future__ import annotations

import asyncio

from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.spider_result import SpiderResult
from platform_core.models.spider_task import SpiderTask

PULL = "/external/v1/public/data"
EVENTS = "/api/v1/product-events"
BANNED = "当前可买"


def _seed_results(db_session, tid: int, spider: str, marker: str, count: int = 1) -> None:
    async def _go():
        async with db_session() as s:
            task = SpiderTask(
                tenant_id=tid, spider_name=spider, status="completed", params="{}",
            )
            s.add(task)
            await s.flush()
            for i in range(count):
                s.add(SpiderResult(
                    task_id=int(task.id), tenant_id=tid, spider_name=spider,
                    url=f"https://{marker}.example/{i}", title=f"{marker}-{i}",
                    source="web",
                ))
            await s.commit()

    asyncio.run(_go())


def _pull(db_client, spider: str, key: str):
    return db_client.get(f"{PULL}/{spider}", headers={"X-API-Key": key})


def _issue_ok(db_client, headers, name: str = "管道") -> str:
    resp = db_client.post("/api/v1/outbound/keys", headers=headers, json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["plaintext_key"]


def _assert_zero_rows(resp, raw: str) -> None:
    assert resp.status_code == 401, resp.text
    body = resp.json()
    assert body.get("items") in (None, [])
    blob = resp.text
    assert raw not in blob
    assert BANNED not in blob


def test_gwt_m20_1_outbound_key_pulls_own_rows(db_client, db_session):
    from test_outbound_keys import _make_member_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="m20-1")
    op, _ = _make_member_headers(db_session, tid, "operator", "m20-1-op")
    _seed_results(db_session, tid, "alpha", "owned")
    raw = _issue_ok(db_client, op)
    resp = _pull(db_client, "alpha", raw)
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] >= 1
    assert any("owned" in (i.get("url") or "") for i in resp.json()["items"])


def test_gwt_m20_4_relay_sk_rejected_zero_rows(db_client, db_session, monkeypatch):
    from test_relay_token_gateway import _create_group, _stub_generate
    from backend.tests.relay_sku_support import seed_relay_sku

    owner, tid = make_tenant_owner_headers(db_session, slug="m20-4")
    seed_relay_sku(db_session, tid)
    _stub_generate(monkeypatch, reply={"key": "sk-m20-4-token", "token_id": "tok-m20-4"})
    gid = _create_group(db_client, owner, db_session, tid)
    issued = db_client.post(
        "/api/v1/relay/tokens", headers=owner,
        json={"group_id": gid, "name": "ci", "quota_tokens": 1000},
    )
    assert issued.status_code == 201, issued.text
    sk = issued.json()["data"]["plaintext_key"]
    _seed_results(db_session, tid, "alpha", "owned")
    resp = _pull(db_client, "alpha", sk)
    _assert_zero_rows(resp, sk)
    listed = db_client.get("/api/v1/outbound/keys", headers=owner)
    assert listed.json()["data"] == []


def test_gwt_m20_5_api_key_and_garbage_rejected(db_client, db_session):
    from test_outbound_keys import _make_member_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="m20-5")
    op, _ = _make_member_headers(db_session, tid, "operator", "m20-5-op")
    _seed_results(db_session, tid, "alpha", "owned")
    created = db_client.post(
        "/api/v1/api-keys", headers=op, json={"name": "legacy"},
    )
    assert created.status_code in (200, 201), created.text
    legacy = created.json()["data"].get("plaintext") or created.json()["data"].get("plaintext_key")
    assert legacy
    resp = _pull(db_client, "alpha", legacy)
    _assert_zero_rows(resp, legacy)
    garbage = _pull(db_client, "alpha", "totally-not-a-key")
    _assert_zero_rows(garbage, "totally-not-a-key")


def test_gwt_m20_5_key_bindings_cannot_pull(db_client, db_session):
    from config import settings

    _, tid = make_tenant_owner_headers(db_session, slug="m20-5b")
    _seed_results(db_session, tid, "alpha", "bound")
    original = settings.get("EXTERNAL_API.KEY_BINDINGS", [])
    settings.set("EXTERNAL_API.KEY_BINDINGS", [
        {"key": "cfg-bound-m20", "tenant_id": int(tid)},
    ])
    try:
        resp = _pull(db_client, "alpha", "cfg-bound-m20")
    finally:
        settings.set("EXTERNAL_API.KEY_BINDINGS", original)
    _assert_zero_rows(resp, "cfg-bound-m20")


def test_gwt_m20_8_page_size_capped_at_100(db_client, db_session):
    from test_outbound_keys import _make_member_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="m20-8")
    op, _ = _make_member_headers(db_session, tid, "operator", "m20-8-op")
    _seed_results(db_session, tid, "alpha", "cap", count=101)
    raw = _issue_ok(db_client, op)
    resp = db_client.get(
        f"{PULL}/alpha", headers={"X-API-Key": raw}, params={"page_size": 101},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) <= 100


def test_gwt_m26_1_reject_event_no_plaintext(db_client, db_session, monkeypatch):
    from test_relay_token_gateway import _create_group, _stub_generate
    from backend.tests.relay_sku_support import seed_relay_sku

    owner, tid = make_tenant_owner_headers(db_session, slug="m26-1")
    seed_relay_sku(db_session, tid)
    _stub_generate(monkeypatch, reply={"key": "sk-m26-1-token", "token_id": "tok-m26-1"})
    gid = _create_group(db_client, owner, db_session, tid)
    issued = db_client.post(
        "/api/v1/relay/tokens", headers=owner,
        json={"group_id": gid, "name": "ci", "quota_tokens": 1000},
    )
    sk = issued.json()["data"]["plaintext_key"]
    _seed_results(db_session, tid, "alpha", "owned")
    _pull(db_client, "alpha", sk)
    pa = make_platform_admin_headers(db_session)
    resp = db_client.get(
        EVENTS, headers=pa,
        params={"event_name": "outbound_wrong_plane_rejected", "tenant_id": tid},
    )
    assert resp.status_code == 200, resp.text
    rows = [
        r for r in resp.json()["data"]["items"]
        if r["event_name"] == "outbound_wrong_plane_rejected"
    ]
    assert rows, resp.text
    assert rows[0]["tenant_id"] == tid
    blob = str(rows)
    assert sk not in blob
    assert "sk-m26" not in blob
    tenant = db_client.get(EVENTS, headers=owner)
    assert tenant.status_code == 404


def test_gwt_m26_2_empty_filter_is_zero_not_error(db_client, db_session):
    """GWT-M26.2：超管筛 outbound_wrong_plane_rejected 且本周无行 → 200 total=0，不是查询失败。"""
    pa = make_platform_admin_headers(db_session)
    resp = db_client.get(
        EVENTS, headers=pa, params={"event_name": "outbound_wrong_plane_rejected"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("success") is True or body.get("code") == "SUCCESS"
    data = body["data"]
    assert data["total"] == 0
    assert data["items"] == []
    assert "失败" not in (body.get("message") or "")
    assert body.get("code") not in {"QUERY_FAILED", "HTTP_500", "INTERNAL_ERROR"}
