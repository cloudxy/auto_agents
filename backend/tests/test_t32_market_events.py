"""T-32 FR-43 市场事件可查：GWT-43.1…43.10。事件名原样；coming_soon 字面量。"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from backend.services.power_market import MARKET_COMING_SOON_CODE
from backend.tests.t25_support import (
    bind_actor,
    seed_listed,
    seed_tenant,
    subscribe_url,
)
from conftest import make_platform_admin_headers, make_tenant_owner_headers

QUERY = "/api/v1/product-events"
PUBLIC = "/api/v1/public/capabilities"
INSTALLS = "/api/v1/capabilities/installs"
LISTING = "/api/v1/capabilities/{}/{}/listing"
SOURCES = "/api/v1/capabilities/sources"


class _RateRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        return True

    async def set(self, *args, **kwargs):
        return True

    async def eval(self, *args, **kwargs):
        return 1

    async def delete(self, key):
        return 1


@pytest.fixture
def rate(monkeypatch):
    fake = _RateRedis()

    async def _fake(key: str = "DEFAULT"):
        return fake

    import backend.app.api.v1.public_skills as pub
    monkeypatch.setattr(pub, "get_async_redis", _fake)
    return fake


@pytest.fixture
def tid(db_session) -> int:
    return seed_tenant(db_session, "t32-op")


@pytest.fixture
def op_client(app, db_client, tid):
    bind_actor(app, role="operator", tenant_id=tid, tenant_role="operator")
    return db_client


def _query(client, headers, **params):
    return client.get(
        QUERY, headers=headers,
        params={k: v for k, v in params.items() if v is not None},
    )


def _items(resp, name=None):
    rows = resp.json()["data"]["items"]
    return [r for r in rows if name is None or r["event_name"] == name]


def _admin_headers(db_session):
    return make_platform_admin_headers(db_session)


def test_gwt_43_1_market_subscribe_succeeded(op_client, db_engine, db_session, tid):
    seed_listed(db_session, name="g431-skill")
    resp = op_client.post(subscribe_url("skill", "g431-skill"), json={"host": "grok"})
    assert resp.status_code == 200, resp.text
    rows = _items(_query(op_client, _admin_headers(db_session), event_name="market_subscribe_succeeded"),
                  "market_subscribe_succeeded")
    assert rows, resp.text
    assert any(r["tenant_id"] == tid and (r.get("props") or {}).get("host") == "grok" for r in rows)


def test_gwt_43_2_coming_soon_rejected_reason(op_client, db_engine, db_session, tid):
    seed_listed(db_session, name="g432-soon", listing_state="coming_soon")
    resp = op_client.post(subscribe_url("skill", "g432-soon"), json={"host": "grok"})
    assert resp.json()["code"] == MARKET_COMING_SOON_CODE
    rows = _items(_query(op_client, _admin_headers(db_session), event_name="market_subscribe_rejected"),
                  "market_subscribe_rejected")
    assert rows
    reason = (rows[0].get("props") or {}).get("reason")
    assert reason == "coming_soon"
    assert reason not in ("preview", "unlisted")


def test_gwt_43_3_tenant_query_is_404_shell(db_client, db_session):
    tenant_headers, _ = make_tenant_owner_headers(db_session, slug="co-43-3")
    resp = _query(db_client, tenant_headers, event_name="market_subscribe_succeeded")
    assert resp.status_code == 404
    assert resp.json()["code"] == "HTTP_404"
    assert "market_subscribe_succeeded" not in resp.text


def test_gwt_43_4_market_list_viewed(db_client, db_engine, db_session, rate):
    seed_listed(db_session, name="g434-skill", category="cat-a")
    listed = db_client.get(PUBLIC, params={"type": "skill", "host": "grok", "category": "cat-a"})
    assert listed.status_code == 200, listed.text
    rows = _items(_query(db_client, _admin_headers(db_session), event_name="market_list_viewed"),
                  "market_list_viewed")
    assert rows
    props = rows[0].get("props") or {}
    assert props.get("type") == "skill"
    assert props.get("host") == "grok"
    assert props.get("category") == "cat-a"


def test_gwt_43_5_market_search_submitted(db_client, db_engine, db_session, rate):
    seed_listed(db_session, name="g435-skill", title="检索卡")
    listed = db_client.get(PUBLIC, params={"q": "检索卡"})
    assert listed.status_code == 200, listed.text
    total = listed.json()["data"]["total"]
    rows = _items(_query(db_client, _admin_headers(db_session), event_name="market_search_submitted"),
                  "market_search_submitted")
    assert rows
    props = rows[0].get("props") or {}
    assert props.get("q") == "检索卡"
    assert props.get("result_count") == total


def test_gwt_43_6_market_detail_viewed(db_client, db_engine, db_session, rate):
    seed_listed(db_session, name="g436-listed")
    seed_listed(db_session, name="g436-soon", listing_state="coming_soon")
    a = db_client.get(f"{PUBLIC}/skill/g436-listed")
    b = db_client.get(f"{PUBLIC}/skill/g436-soon")
    assert a.status_code == b.status_code == 200
    rows = _items(_query(db_client, _admin_headers(db_session), event_name="market_detail_viewed"),
                  "market_detail_viewed")
    types = {(r.get("props") or {}).get("type") for r in rows}
    listing = {(r.get("props") or {}).get("listing_state") for r in rows}
    assert "skill" in types
    assert "listed" in listing
    assert "coming_soon" in listing


def test_gwt_43_7_market_uninstalled(op_client, db_engine, db_session, tid):
    seed_listed(db_session, name="g437-skill")
    assert op_client.post(subscribe_url("skill", "g437-skill"), json={"host": "claude"}).status_code == 200
    items = op_client.get(INSTALLS).json()["data"]["items"]
    iid = next(r["id"] for r in items if r["asset_name"] == "g437-skill")
    gone = op_client.delete(f"{INSTALLS}/{iid}")
    assert gone.status_code == 200, gone.text
    rows = _items(_query(op_client, _admin_headers(db_session), event_name="market_uninstalled"),
                  "market_uninstalled")
    assert rows
    assert any((r.get("props") or {}).get("host") == "claude" for r in rows)


def test_gwt_43_8_market_listing_changed(
    db_client, platform_admin_client, db_engine, db_session,
):
    seed_listed(db_session, name="g438-row", listing_state="unlisted")
    resp = platform_admin_client.patch(
        LISTING.format("skill", "g438-row"), json={"listing_state": "listed"},
    )
    assert resp.status_code == 200, resp.text
    rows = _items(
        platform_admin_client.get(QUERY, params={"event_name": "market_listing_changed"}),
        "market_listing_changed",
    )
    assert rows
    props = rows[0].get("props") or {}
    assert props.get("old_state") == "unlisted"
    assert props.get("new_state") == "listed"


def test_gwt_43_9_market_source_sync_completed(
    db_client, platform_admin_client, db_engine, db_session, tmp_path: Path,
):
    from config import settings

    original = settings.get("SKILLS.LIBRARY_ROOT")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))
    plugin = tmp_path / "pack-t32"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(json.dumps({
        "name": "pack-t32", "description": "pack-t32", "version": "1.0.0", "license": "MIT",
    }), encoding="utf-8")
    created = platform_admin_client.post(SOURCES, json={
        "name": "src-t32", "source_kind": "local", "uri": str(tmp_path),
    })
    assert created.status_code in (200, 201), created.text
    synced = platform_admin_client.post(f"{SOURCES}/src-t32/sync")
    settings.set("SKILLS.LIBRARY_ROOT", original)
    assert synced.status_code == 200, synced.text
    body = synced.json()["data"]
    rows = _items(
        platform_admin_client.get(QUERY, params={"event_name": "market_source_sync_completed"}),
        "market_source_sync_completed",
    )
    assert rows
    props = rows[0].get("props") or {}
    assert props.get("succeeded") == body["succeeded"]
    assert props.get("failed") == body["failed"]


def test_gwt_43_10_filter_by_tenant_a(app, db_client, db_engine, db_session):
    tid_a = seed_tenant(db_session, "t32-a")
    tid_b = seed_tenant(db_session, "t32-b")
    seed_listed(db_session, name="g4310-a")
    seed_listed(db_session, name="g4310-b")
    bind_actor(app, role="operator", tenant_id=tid_a, tenant_role="operator")
    assert db_client.post(subscribe_url("skill", "g4310-a"), json={"host": "grok"}).status_code == 200
    bind_actor(app, role="operator", tenant_id=tid_b, tenant_role="operator")
    assert db_client.post(subscribe_url("skill", "g4310-b"), json={"host": "kimi"}).status_code == 200
    rows = _items(
        _query(db_client, _admin_headers(db_session),
               event_name="market_subscribe_succeeded", tenant_id=tid_a),
        "market_subscribe_succeeded",
    )
    assert rows
    assert all(r["tenant_id"] == tid_a for r in rows)
    assert not any(r["tenant_id"] == tid_b for r in rows)


def test_emit_failure_does_not_block_subscribe(op_client, db_engine, db_session, tid, monkeypatch):
    seed_listed(db_session, name="g43-fail")
    monkeypatch.setattr(
        "backend.services.product_event_service._persist_event",
        AsyncMock(side_effect=RuntimeError("events down")),
    )
    resp = op_client.post(subscribe_url("skill", "g43-fail"), json={"host": "grok"})
    assert resp.status_code == 200, resp.text
    rows = _items(_query(op_client, _admin_headers(db_session), event_name="market_subscribe_succeeded"),
                  "market_subscribe_succeeded")
    assert rows == []
