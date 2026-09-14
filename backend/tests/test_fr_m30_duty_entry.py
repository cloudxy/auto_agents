"""T-18 / FR-M30 M34 M35：值班单一入口；租户 404；签发≠live；duty_entry_opened。"""
from __future__ import annotations

from conftest import make_platform_admin_headers, make_tenant_owner_headers

DUTY = "/api/v1/newapi/overview"
KEYS = "/api/v1/litellm/keys"
EVENTS = "/api/v1/product-events"
GHOST = "/api/v1/admin/tenants"
SORRY = "抱歉您没有权限"
LIVE = ("网关已对租户开通", "当前可买", "C2")


def _same_404(resp, ghost) -> None:
    assert resp.status_code == ghost.status_code == 404
    assert resp.json()["code"] == ghost.json()["code"] == "HTTP_404"
    assert resp.json()["message"] == ghost.json()["message"] == "Not Found"
    assert SORRY not in resp.text
    assert "FORBIDDEN" not in (resp.json().get("message") or "")


def test_gwt_m30_3_tenant_duty_is_404(db_client, db_session):
    owner, _ = make_tenant_owner_headers(db_session, slug="m30-3")
    ghost = db_client.get(GHOST, headers=owner)
    duty = db_client.get(DUTY, headers=owner)
    _same_404(duty, ghost)


def test_gwt_m30_4_tenant_litellm_keys_404_not_403(db_client, db_session):
    owner, _ = make_tenant_owner_headers(db_session, slug="m30-4")
    ghost = db_client.get(GHOST, headers=owner)
    keys = db_client.get(KEYS, headers=owner)
    _same_404(keys, ghost)


def test_gwt_m35_1_superadmin_open_emits_duty_entry(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    opened = db_client.get(DUTY, headers=pa)
    assert opened.status_code == 200, opened.text
    blob = opened.text
    for word in LIVE:
        assert word not in blob
    rows = db_client.get(
        EVENTS, headers=pa, params={"event_name": "duty_entry_opened"},
    )
    assert rows.status_code == 200, rows.text
    items = [r for r in rows.json()["data"]["items"] if r["event_name"] == "duty_entry_opened"]
    assert items
    assert items[0].get("actor_user_id")
    assert "sk-" not in str(items[0].get("props") or {})


def test_gwt_m35_2_tenant_open_does_not_emit_success(db_client, db_session):
    owner, _ = make_tenant_owner_headers(db_session, slug="m35-2")
    pa = make_platform_admin_headers(db_session)
    before = db_client.get(
        EVENTS, headers=pa, params={"event_name": "duty_entry_opened"},
    ).json()["data"]["total"]
    db_client.get(DUTY, headers=owner)
    after = db_client.get(
        EVENTS, headers=pa, params={"event_name": "duty_entry_opened"},
    ).json()["data"]["total"]
    assert after == before


def test_gwt_m35_3_tenant_cannot_query_duty_event(db_client, db_session):
    owner, _ = make_tenant_owner_headers(db_session, slug="m35-3")
    resp = db_client.get(EVENTS, headers=owner, params={"event_name": "duty_entry_opened"})
    assert resp.status_code == 404
    assert "duty_entry_opened" not in resp.text
