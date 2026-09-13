"""T-15 FR-U31：超管商户凭据 Fernet 落库、读回掩码、轮换、租户 404 同形。"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from backend.services.llm_secret_vault import LlmSecretVault
from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.payment_channel_credential import PaymentChannelCredential
from platform_core.schemas.payment_channel_credential import SECRETS_MASK

CRED = "/api/v1/admin/payment-credentials"
GHOST = "/api/v1/admin/tenants"
SORRY = "抱歉您没有权限"
CONFIG = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch):
    monkeypatch.setenv("LLM_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _cred_row(db_session, channel: str):
    async def _go():
        async with db_session() as s:
            return (await s.execute(
                select(PaymentChannelCredential).where(
                    PaymentChannelCredential.channel == channel,
                )
            )).scalar_one_or_none()

    return asyncio.run(_go())


def _assert_missing_shape(resp, ghost):
    assert resp.status_code == ghost.status_code == 404, resp.text
    body, other = resp.json(), ghost.json()
    assert body["code"] == other["code"] == "HTTP_404"
    assert body["message"] == other["message"] == "Not Found"
    assert "FORBIDDEN" not in body["code"]
    assert SORRY not in resp.text


def _put(db_client, headers, channel, merchant, secret):
    return db_client.put(CRED, headers=headers, json={
        "channel": channel, "merchant_no": merchant, "secrets": secret,
    })


def test_gwt_u31_2_empty_form_both_unconfigured(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    resp = db_client.get(CRED, headers=pa)
    assert resp.status_code == 200, resp.text
    channels = resp.json()["data"]["channels"]
    assert [c["channel"] for c in channels] == ["alipay", "wechat"]
    for item in channels:
        assert item["configured"] is False
        assert item["secrets_masked"] is None
        assert item["merchant_no"] is None
    assert "secrets_encrypted" not in resp.text
    assert "当前可买" not in resp.text


def test_gwt_u31_1_save_then_get_masks_secret(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    secret = "sk-t15-" + uuid.uuid4().hex
    saved = _put(db_client, pa, "alipay", "208812345", secret)
    assert saved.status_code == 200, saved.text
    data = saved.json()["data"]
    assert data["configured"] is True
    assert data["merchant_no"] == "208812345"
    assert data["secrets_masked"] == SECRETS_MASK
    assert data["key_version"] == 1
    assert secret not in saved.text
    assert "secrets_encrypted" not in saved.text

    opened = db_client.get(CRED, headers=pa)
    assert opened.status_code == 200, opened.text
    body = opened.json()
    alipay = next(c for c in body["data"]["channels"] if c["channel"] == "alipay")
    assert alipay["merchant_no"] == "208812345"
    assert alipay["secrets_masked"] == SECRETS_MASK
    assert secret not in opened.text
    assert secret not in str(body)
    row = _cred_row(db_session, "alipay")
    assert row is not None
    assert row.secrets_encrypted != secret
    assert LlmSecretVault.decrypt_api_key(row.secrets_encrypted) == secret


def test_gwt_u31_3_tenant_404_same_shape_no_secret(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    secret = "sk-t15-tenant-" + uuid.uuid4().hex
    assert _put(db_client, pa, "wechat", "mch-1", secret).status_code == 200
    owner, _tid = make_tenant_owner_headers(db_session, slug="u31-3")
    ghost = db_client.get(GHOST, headers=owner)
    listed = db_client.get(CRED, headers=owner)
    _assert_missing_shape(listed, ghost)
    assert secret not in listed.text
    put = _put(db_client, owner, "alipay", "2088hack", secret + "x")
    _assert_missing_shape(put, ghost)
    assert secret + "x" not in put.text
    row = _cred_row(db_session, "wechat")
    assert row is not None
    assert row.merchant_no == "mch-1"
    assert _cred_row(db_session, "alipay") is None


def test_gwt_u31_4_secret_not_in_config_or_git(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    secret = "sk-t15-git-" + uuid.uuid4().hex
    assert _put(db_client, pa, "alipay", "2088git", secret).status_code == 200
    for path in CONFIG.rglob("*.yml"):
        text = path.read_text(encoding="utf-8")
        assert secret not in text
        lower = text.lower()
        for banned in (
            "alipay_private_key", "alipay_app_secret", "wechat_mch_key",
            "wechat_api_v3_key", "wxpay_key",
        ):
            assert banned not in lower, path
    opened = db_client.get(CRED, headers=pa)
    assert secret not in opened.text


def test_gwt_u31_5_rotate_drops_old_secret(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    old = "sk-t15-old-" + uuid.uuid4().hex
    new = "sk-t15-new-" + uuid.uuid4().hex
    first = _put(db_client, pa, "alipay", "2088a", old)
    assert first.status_code == 200, first.text
    blob1 = _cred_row(db_session, "alipay").secrets_encrypted
    rotated = _put(db_client, pa, "alipay", "2088b", new)
    assert rotated.status_code == 200, rotated.text
    data = rotated.json()["data"]
    assert data["key_version"] == 2
    assert data["rotated_at"] is not None
    assert data["merchant_no"] == "2088b"
    assert old not in rotated.text and new not in rotated.text
    row = _cred_row(db_session, "alipay")
    assert row.secrets_encrypted != blob1
    assert row.secrets_encrypted != old
    assert LlmSecretVault.decrypt_api_key(row.secrets_encrypted) == new
    assert LlmSecretVault.decrypt_api_key(row.secrets_encrypted) != old


def test_delete_unconfigures_channel(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    secret = "sk-t15-del-" + uuid.uuid4().hex
    assert _put(db_client, pa, "wechat", "mch-del", secret).status_code == 200
    deleted = db_client.delete(f"{CRED}/wechat", headers=pa)
    assert deleted.status_code == 200, deleted.text
    assert _cred_row(db_session, "wechat") is None
    listed = db_client.get(CRED, headers=pa)
    wechat = next(c for c in listed.json()["data"]["channels"] if c["channel"] == "wechat")
    assert wechat["configured"] is False
    assert secret not in listed.text


def test_put_rejects_unknown_channel(db_client, db_session):
    pa = make_platform_admin_headers(db_session)
    resp = _put(db_client, pa, "paypal", "m", "secret-x")
    assert resp.status_code == 422
    assert _cred_row(db_session, "paypal") is None


def test_put_without_master_key_does_not_store_plaintext(db_client, db_session, monkeypatch):
    monkeypatch.delenv("LLM_ENCRYPTION_KEY", raising=False)
    from stubs import fake_settings
    monkeypatch.setattr("backend.services.llm_secret_vault.settings", fake_settings())
    pa = make_platform_admin_headers(db_session)
    secret = "sk-t15-plain-" + uuid.uuid4().hex
    resp = _put(db_client, pa, "alipay", "2088x", secret)
    assert resp.status_code == 400, resp.text
    assert _cred_row(db_session, "alipay") is None
