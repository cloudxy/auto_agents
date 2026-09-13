"""T-08 FR-U10/U11/U14：POWER_MARKET.ENABLED 运行时闸订一行与关闭句。"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from backend.services.power_market import (
    MARKET_CLOSED_CODE,
    MARKET_COMING_SOON_CODE,
    MARKET_READONLY_ROLE_CODE,
    MSG_EMPTY_SHELF,
    MSG_MARKET_CLOSED,
    is_power_market_enabled,
)
from backend.tests.fr33_support import seed_include_parent
from backend.tests.t25_support import (
    asset_id_of,
    bind_actor,
    live_install_count,
    live_installs,
    seed_listed,
    seed_tenant,
    subscribe_url,
)
from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.capability import CapabilityAsset

PUBLIC = "/api/v1/public/capabilities"
PUBLIC_SKILLS = "/api/v1/public/skills"
EVENTS = "/api/v1/product-events"
SWITCH = "/api/v1/admin/power-market"
INSTALLS = "/api/v1/capabilities/installs"
SHELF = "暂无已上架能力"
CLOSED = "能力市场未开放"
LOAD_FAIL = "加载失败"


class _RateRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        return True


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
    return seed_tenant(db_session, "u10-op")


@pytest.fixture
def op_client(app, db_client, tid):
    bind_actor(app, role="operator", tenant_id=tid, tenant_role="operator")
    return db_client


def _close_market():
    from config import settings

    settings.set("POWER_MARKET.ENABLED", False)


def _items(resp, name=None):
    rows = resp.json()["data"]["items"]
    return [r for r in rows if name is None or r["event_name"] == name]


def test_gwt_u10_1_subscribe_one_row_no_children(op_client, db_session, tid):
    seed_include_parent(db_session, parent="u101-plug", children=[
        {"name": "u101-s1"}, {"name": "u101-s2"},
    ])
    resp = op_client.post(subscribe_url("plugin", "u101-plug"), json={"host": "grok"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["created"] is True
    listed = op_client.get(INSTALLS)
    names = [i["asset_name"] for i in listed.json()["data"]["items"]]
    assert names == ["u101-plug"]
    rows = live_installs(db_session)
    assert len(rows) == 1
    assert rows[0].asset_id == asset_id_of(db_session, "u101-plug")
    child_ids = {asset_id_of(db_session, n) for n in ("u101-s1", "u101-s2")}
    assert rows[0].asset_id not in child_ids


def test_gwt_u10_2_open_empty_shelf_not_closed(db_client, rate):
    for path in (PUBLIC, PUBLIC_SKILLS):
        resp = db_client.get(path)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["items"] == []
        assert data.get("empty") is True
        assert MSG_EMPTY_SHELF in (data.get("message") or "")
        assert SHELF in resp.text
        assert CLOSED not in resp.text
        assert LOAD_FAIL not in resp.text
        assert data.get("market_closed") is False


def test_gwt_u10_3_readonly_rejected(app, db_client, db_session, tid):
    bind_actor(app, role="viewer", tenant_id=tid, tenant_role="viewer")
    seed_listed(db_session, name="u103-skill")
    resp = db_client.post(subscribe_url("skill", "u103-skill"), json={"host": "grok"})
    assert resp.json()["code"] == MARKET_READONLY_ROLE_CODE
    assert live_install_count(db_session) == 0


def test_gwt_u10_4_coming_soon_not_subscribable(op_client, db_client, db_session, rate):
    seed_listed(db_session, name="u104-soon", listing_state="coming_soon")
    listed = db_client.get(PUBLIC)
    by_name = {i["name"]: i for i in listed.json()["data"]["items"]}
    assert by_name["u104-soon"]["subscribable"] is False
    detail = db_client.get(f"{PUBLIC}/skill/u104-soon")
    assert detail.json()["data"]["subscribable"] is False
    resp = op_client.post(subscribe_url("skill", "u104-soon"), json={"host": "grok"})
    assert resp.json()["code"] == MARKET_COMING_SOON_CODE
    assert live_install_count(db_session) == 0


def test_gwt_u11_1_closed_subscribe_no_row(op_client, db_session, tid):
    _close_market()
    seed_listed(db_session, name="u111-skill")
    resp = op_client.post(subscribe_url("skill", "u111-skill"), json={"host": "grok"})
    assert resp.json()["code"] == MARKET_CLOSED_CODE
    assert MSG_MARKET_CLOSED in resp.json()["message"]
    assert live_install_count(db_session) == 0
    assert op_client.get(INSTALLS).json()["data"]["items"] == []


def test_gwt_u11_2_closed_list_not_empty_shelf(db_client, db_session, rate):
    _close_market()
    seed_listed(db_session, name="u112-skill")
    for path in (PUBLIC, PUBLIC_SKILLS):
        resp = db_client.get(path)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["items"] == []
        assert data.get("market_closed") is True
        assert MSG_MARKET_CLOSED in (data.get("message") or "")
        assert CLOSED in resp.text
        assert SHELF not in resp.text
    detail = db_client.get(f"{PUBLIC}/skill/u112-skill")
    assert detail.status_code == 200, detail.text
    body = detail.json()["data"]
    assert body.get("market_closed") is True
    assert MSG_MARKET_CLOSED in (body.get("message") or "")
    assert SHELF not in detail.text
    assert "u112-skill" not in (body.get("name") or "")


def test_gwt_u11_3_tenant_admin_cannot_flip(
    admin_client, db_session, db_client, rate,
):
    _close_market()
    seed_listed(db_session, name="u113-skill")
    before = [r.listing_state for r in _assets(db_session)]
    resp = admin_client.put(SWITCH, json={"enabled": True})
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"
    assert is_power_market_enabled() is False
    after = [r.listing_state for r in _assets(db_session)]
    assert after == before
    assert live_install_count(db_session) == 0
    listed = db_client.get(PUBLIC)
    assert listed.json()["data"].get("market_closed") is True


def test_platform_admin_can_flip_switch(platform_admin_client):
    _close_market()
    got = platform_admin_client.get(SWITCH)
    assert got.status_code == 200, got.text
    assert got.json()["data"]["enabled"] is False
    opened = platform_admin_client.put(SWITCH, json={"enabled": True})
    assert opened.status_code == 200, opened.text
    assert opened.json()["data"]["enabled"] is True
    assert is_power_market_enabled() is True


def test_gwt_u14_1_subscribe_event_queryable(op_client, db_session, tid):
    seed_listed(db_session, name="u141-skill")
    resp = op_client.post(subscribe_url("skill", "u141-skill"), json={"host": "grok"})
    assert resp.status_code == 200, resp.text
    headers = make_platform_admin_headers(db_session)
    queried = op_client.get(
        EVENTS,
        headers=headers,
        params={"event_name": "market_subscribe_succeeded", "tenant_id": tid},
    )
    assert queried.status_code == 200, queried.text
    rows = _items(queried, "market_subscribe_succeeded")
    assert rows
    assert any(
        r["tenant_id"] == tid and (r.get("props") or {}).get("host") == "grok"
        for r in rows
    )


def test_gwt_u14_2_closed_attempt_no_succeeded(op_client, db_session, tid):
    _close_market()
    seed_listed(db_session, name="u142-skill")
    resp = op_client.post(subscribe_url("skill", "u142-skill"), json={"host": "grok"})
    assert resp.json()["code"] == MARKET_CLOSED_CODE
    headers = make_platform_admin_headers(db_session)
    queried = op_client.get(
        EVENTS,
        headers=headers,
        params={"event_name": "market_subscribe_succeeded", "tenant_id": tid},
    )
    assert queried.status_code == 200
    assert _items(queried, "market_subscribe_succeeded") == []


def test_gwt_u14_3_tenant_query_events_404(db_client, db_session):
    tenant_headers, _ = make_tenant_owner_headers(db_session, slug="co-u14-3")
    resp = db_client.get(
        EVENTS, headers=tenant_headers,
        params={"event_name": "market_subscribe_succeeded"},
    )
    ghost = db_client.get("/api/v1/admin/tenants", headers=tenant_headers)
    assert resp.status_code == ghost.status_code == 404
    assert resp.json()["code"] == ghost.json()["code"] == "HTTP_404"
    assert "抱歉" not in resp.text
    assert "market_subscribe_succeeded" not in resp.text


def _assets(db_session):
    import asyncio

    async def _go():
        async with db_session() as s:
            return list((await s.execute(select(CapabilityAsset))).scalars().all())

    return asyncio.run(_go())
