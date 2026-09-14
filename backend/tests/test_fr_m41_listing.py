"""T-23 / FR-M41：超管上架/下架一行；无投稿入口；下架不级联删安装。"""
from __future__ import annotations

import pytest

from backend.services.power_market import MSG_MARKET_CLOSED
from backend.tests.t25_support import live_install_count, seed_listed, subscribe_url
from conftest import make_platform_admin_headers, make_tenant_owner_headers

LISTING = "/api/v1/capabilities/skill/{}/listing"
PUBLIC = "/api/v1/public/capabilities"
CATALOG = "/api/v1/capabilities"
INSTALLS = "/api/v1/capabilities/installs"
GHOST = "/api/v1/admin/tenants"
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


SUBMIT = "/api/v1/capabilities/submit"
PUBLISH = "/api/v1/public/capabilities/publish"
AUTHOR = "/api/v1/capabilities/author"


def test_gwt_m41_1_superadmin_list_then_public_visible(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    seed_listed(db_session, name="m41-1-row", listing_state="unlisted")
    listed = db_client.patch(
        LISTING.format("m41-1-row"), headers=pa, json={"listing_state": "listed"},
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["listing_state"] == "listed"
    pub = db_client.get(PUBLIC)
    assert pub.status_code == 200, pub.text
    names = [i["name"] for i in pub.json()["data"]["items"]]
    assert "m41-1-row" in names
    assert MSG_MARKET_CLOSED not in pub.text
    assert "当前可买" not in pub.text


def test_gwt_m41_2_governance_empty_is_zero_not_fail(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    resp = db_client.get(CATALOG, headers=pa)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["items"] == []
    assert data.get("total") == 0
    blob = resp.text
    assert "投稿" not in blob
    assert "成为作者" not in blob
    assert "发布到能力市场" not in blob
    assert MSG_MARKET_CLOSED not in blob


def test_gwt_m41_3_no_author_portal_tenant_cannot_list(db_client, db_session):
    owner, _ = make_tenant_owner_headers(db_session, slug="m41-3")
    ghost = db_client.get(GHOST, headers=owner)
    seed_listed(db_session, name="m41-3-row", listing_state="unlisted")
    listing = db_client.patch(
        LISTING.format("m41-3-row"), headers=owner, json={"listing_state": "listed"},
    )
    assert listing.status_code == ghost.status_code == 404
    assert listing.json()["code"] == "HTTP_404"
    for path in (SUBMIT, PUBLISH, AUTHOR):
        resp = db_client.post(path, headers=owner, json={"name": "hack"})
        assert resp.status_code == 404
        assert "投稿" not in resp.text
    anon = db_client.post(SUBMIT, json={"name": "hack"})
    assert anon.status_code in (401, 404)


def test_gwt_m41_4_unlist_does_not_cascade_installs(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    owner, _ = make_tenant_owner_headers(db_session, slug="m41-4")
    seed_listed(db_session, name="m41-4-row")
    sub = db_client.post(
        subscribe_url("skill", "m41-4-row"), headers=owner, json={"host": "grok"},
    )
    assert sub.status_code == 200, sub.text
    before = live_install_count(db_session)
    unlisted = db_client.patch(
        LISTING.format("m41-4-row"), headers=pa, json={"listing_state": "unlisted"},
    )
    assert unlisted.status_code == 200, unlisted.text
    assert unlisted.json()["data"]["listing_state"] == "unlisted"
    pub = db_client.get(PUBLIC)
    names = [i["name"] for i in pub.json()["data"]["items"]]
    assert "m41-4-row" not in names
    assert live_install_count(db_session) == before
    mine = db_client.get(INSTALLS, headers=owner)
    assert [i["asset_name"] for i in mine.json()["data"]["items"]] == ["m41-4-row"]
