"""T-22 / FR-M40：租户货架+安装；关旗诚实句；治理七叶 404；跨企业安装 404。"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from backend.services.power_market import MSG_EMPTY_SHELF, MSG_MARKET_CLOSED
from backend.tests.t25_support import live_install_count, seed_listed, subscribe_url
from conftest import make_tenant_owner_headers
from platform_core.models.capability import CapabilityInstall

SHELF = "/api/v1/capabilities"
PUBLIC = "/api/v1/public/capabilities"
INSTALLS = "/api/v1/capabilities/installs"
SOURCES = "/api/v1/capabilities/sources"
LISTING = "/api/v1/capabilities/skill/{}/listing"
GHOST = "/api/v1/admin/tenants"
SORRY = "抱歉您没有权限"
BANNED = "当前可买"


class _RateRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        return True


@pytest.fixture(autouse=True)
def _rate(monkeypatch):
    fake = _RateRedis()

    async def _fake(key: str = "DEFAULT"):
        return fake

    import backend.app.api.v1.public_skills as pub
    monkeypatch.setattr(pub, "get_async_redis", _fake)
    return fake


def _close():
    from config import settings
    settings.set("POWER_MARKET.ENABLED", False)


def _same_404(resp, ghost) -> None:
    assert resp.status_code == ghost.status_code == 404
    assert resp.json()["code"] == ghost.json()["code"] == "HTTP_404"
    assert resp.json()["message"] == ghost.json()["message"] == "Not Found"
    assert SORRY not in resp.text
    assert "FORBIDDEN" not in (resp.json().get("message") or "")


def test_gwt_m40_1_tenant_shelf_listed_and_own_installs(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="m40-1")
    seed_listed(db_session, name="m40-1-on")
    seed_listed(db_session, name="m40-1-off", listing_state="unlisted")
    shelf = db_client.get(SHELF, headers=owner)
    assert shelf.status_code == 200, shelf.text
    names = [i["name"] for i in shelf.json()["data"]["items"]]
    assert "m40-1-on" in names
    assert "m40-1-off" not in names
    assert MSG_MARKET_CLOSED not in shelf.text
    assert BANNED not in shelf.text
    sub = db_client.post(
        subscribe_url("skill", "m40-1-on"), headers=owner, json={"host": "grok"},
    )
    assert sub.status_code == 200, sub.text
    mine = db_client.get(INSTALLS, headers=owner)
    assert mine.status_code == 200, mine.text
    assert [i["asset_name"] for i in mine.json()["data"]["items"]] == ["m40-1-on"]


def test_gwt_m40_2_flag_off_is_closed_not_empty_shelf(db_client, db_session):
    _close()
    owner, _ = make_tenant_owner_headers(db_session, slug="m40-2")
    seed_listed(db_session, name="m40-2-skill")
    for path in (SHELF, PUBLIC):
        resp = db_client.get(path, headers=owner)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["items"] == []
        assert MSG_MARKET_CLOSED in (data.get("message") or "")
        assert MSG_EMPTY_SHELF not in resp.text
        assert "还没有目录项" not in resp.text
        assert BANNED not in resp.text
    sub = db_client.post(
        subscribe_url("skill", "m40-2-skill"), headers=owner, json={"host": "grok"},
    )
    assert sub.status_code == 409
    assert MSG_MARKET_CLOSED in sub.json()["message"]
    assert live_install_count(db_session) == 0


def test_gwt_m40_3_tenant_governance_is_404(db_client, db_session):
    owner, _ = make_tenant_owner_headers(db_session, slug="m40-3")
    seed_listed(db_session, name="m40-3-row", listing_state="unlisted")
    ghost = db_client.get(GHOST, headers=owner)
    listing = db_client.patch(
        LISTING.format("m40-3-row"), headers=owner, json={"listing_state": "listed"},
    )
    _same_404(listing, ghost)
    _same_404(db_client.get(SOURCES, headers=owner), ghost)
    _same_404(db_client.post("/api/v1/capabilities/sync-agents-hub", headers=owner), ghost)
    _same_404(db_client.post("/api/v1/capabilities/import", headers=owner), ghost)


def test_gwt_m40_4_coming_soon_subscribe_no_install(db_client, db_session):
    owner, _ = make_tenant_owner_headers(db_session, slug="m40-4")
    seed_listed(db_session, name="m40-4-soon", listing_state="coming_soon")
    resp = db_client.post(
        subscribe_url("skill", "m40-4-soon"), headers=owner, json={"host": "grok"},
    )
    assert resp.status_code == 409
    assert live_install_count(db_session) == 0


def test_gwt_m40_cross_tenant_install_404(db_client, db_session):
    a, tid_a = make_tenant_owner_headers(db_session, slug="m40-xa")
    b, tid_b = make_tenant_owner_headers(db_session, slug="m40-xb")
    seed_listed(db_session, name="m40-x-skill")
    created = db_client.post(
        subscribe_url("skill", "m40-x-skill"), headers=a, json={"host": "grok"},
    )
    assert created.status_code == 200, created.text
    mine = db_client.get(INSTALLS, headers=a)
    iid = mine.json()["data"]["items"][0]["id"]

    async def _check_tenant():
        async with db_session() as s:
            row = (await s.execute(
                select(CapabilityInstall).where(CapabilityInstall.id == iid)
            )).scalar_one()
            assert int(row.tenant_id) == tid_a
            assert int(row.tenant_id) != tid_b

    asyncio.run(_check_tenant())
    ghost = db_client.get(GHOST, headers=b)
    patched = db_client.patch(
        f"{INSTALLS}/{iid}", headers=b, json={"enabled": False},
    )
    _same_404(patched, ghost)
    deleted = db_client.delete(f"{INSTALLS}/{iid}", headers=b)
    _same_404(deleted, ghost)
    assert live_install_count(db_session) == 1
