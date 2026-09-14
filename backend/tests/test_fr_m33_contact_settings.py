"""T-21 / FR-M33：值班联系空则访客无 CTA；设置保存不谎称同步官网；租户写 404。"""
from __future__ import annotations

from conftest import make_platform_admin_headers, make_tenant_owner_headers

PUBLIC = "/api/v1/public/ops-contact"
CONFIGS = "/api/v1/configs"
GHOST = "/api/v1/admin/tenants"
SYNC_LIE = ("官网已同步", "已同步官网", "官网内容已实时同步更新")


def test_gwt_m33_1_empty_contact_is_blank_string(db_client, monkeypatch):
    from config import settings

    prev = settings.get("OPS.DUTY_CONTACT")
    settings.set("OPS.DUTY_CONTACT", "")
    try:
        resp = db_client.get(PUBLIC)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        contact = data.get("duty_contact")
        assert contact in ("", None)
        blob = resp.text
        assert "contact@localhost" not in blob
        assert "值班电话" not in blob
        assert "当前可买" not in blob
    finally:
        settings.set("OPS.DUTY_CONTACT", prev if prev is not None else "")


def test_gwt_m33_2_nonempty_contact_is_visible(db_client, monkeypatch):
    from config import settings

    prev = settings.get("OPS.DUTY_CONTACT")
    settings.set("OPS.DUTY_CONTACT", "ops@example.invalid")
    try:
        resp = db_client.get(PUBLIC)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["duty_contact"] == "ops@example.invalid"
        assert "已接通电话值班" not in resp.text
        assert "当前可买" not in resp.text
    finally:
        settings.set("OPS.DUTY_CONTACT", prev if prev is not None else "")


def test_gwt_m33_3_tenant_cannot_put_contact(db_client, db_session):
    owner, _ = make_tenant_owner_headers(db_session, slug="m33-3")
    before = db_client.get(PUBLIC).json()["data"]["duty_contact"]
    resp = db_client.put(
        f"{CONFIGS}/ops.duty_contact", headers=owner, json={"value": "hack@x.co"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "HTTP_404"
    assert db_client.get(PUBLIC).json()["data"]["duty_contact"] == before


def test_gwt_m33_4_save_does_not_claim_official_synced(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    resp = db_client.put(
        f"{CONFIGS}/site.subtitle", headers=pa, json={"value": "副标题"},
    )
    assert resp.status_code == 200, resp.text
    msg = resp.json()["message"]
    for lie in SYNC_LIE:
        assert lie not in msg
    assert "官网已同步" not in resp.text


def test_gwt_m33_5_tenant_settings_write_404(db_client, db_session):
    owner, _ = make_tenant_owner_headers(db_session, slug="m33-5")
    ghost = db_client.get(GHOST, headers=owner)
    resp = db_client.put(
        f"{CONFIGS}/site.name", headers=owner, json={"value": "hijack"},
    )
    assert resp.status_code == ghost.status_code == 404
    assert resp.json()["code"] == "HTTP_404"
    assert "当前账号不能改系统设置" not in resp.text
