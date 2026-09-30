"""注册邮箱验证（决策 D21 = A 的前置闸之一，2026-09-29「按照建议做」）

免费档可用平台 LLM 做 AI 规划；为防批量注册薅额度：
- 企业自助注册后发验证邮件（链接带签名令牌，3 天有效）；负责人验证前，整个企业不能用 AI 规划
  （按企业判定：未验证的负责人另建成员也绕不过去）
- 已有账号、负责人在企业内新建的成员不受影响
- 重新发送限频（60 秒一次）
"""
from __future__ import annotations

import asyncio
import re

import pytest
from sqlalchemy import select

from platform_core.models.user import User
from stubs import FakeRedis

SIGNUP = "/api/v1/public/tenant/signup"
VERIFY = "/api/v1/auth/verify-email"
RESEND = "/api/v1/auth/resend-verification"
LOGIN = "/api/v1/auth/login"
PLANS = "/api/v1/ai/plans"


@pytest.fixture(autouse=True)
def _no_signup_rate_limit(monkeypatch):
    """与 test_saas_signup_expiry 同一做法：限流语义由 test_b1_rate_limiter.py 专项覆盖"""
    from unittest.mock import AsyncMock

    monkeypatch.setattr("backend.app.api.v1.tenant_signup.enforce_request_limit", AsyncMock(return_value=None))


@pytest.fixture
def mailbox(monkeypatch):
    import backend.services.email_verification_service as svc

    sent: list[tuple[str, str, str]] = []

    async def _send(to, subject, text, html=None):
        sent.append((to, subject, text))
        return True

    monkeypatch.setattr(svc, "send_mail", _send)
    redis = FakeRedis()
    monkeypatch.setattr(svc, "get_async_redis", lambda: redis)
    return sent


def _signup(client, email="boss@acme-d21.cn"):
    resp = client.post(SIGNUP, json={"company": "阿克米", "admin_email": email, "admin_password": "Passw0rd!"})
    assert resp.status_code in (200, 201), resp.text
    return resp


def _login(client, email="boss@acme-d21.cn"):
    resp = client.post(LOGIN, json={"username": email, "password": "Passw0rd!"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _token_from(mail_text: str) -> str:
    m = re.search(r"token=([A-Za-z0-9._\-]+)", mail_text)
    assert m, mail_text
    return m.group(1)


def test_signup_sends_verification_and_blocks_ai_until_verified(db_client, db_session, mailbox):
    _signup(db_client)
    assert len(mailbox) == 1
    to, subject, text = mailbox[0]
    assert to == "boss@acme-d21.cn" and "验证" in subject
    session = _login(db_client)
    assert session["email_verify_pending"] is True
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    blocked = db_client.post(PLANS, headers=headers, json={"target_url": "https://example.com/list"})
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["code"] == "EMAIL_NOT_VERIFIED"

    ok = db_client.post(VERIFY, json={"token": _token_from(text)})
    assert ok.status_code == 200, ok.text
    after = db_client.post(PLANS, headers=headers, json={"target_url": "https://example.com/list"})
    assert after.json().get("code") != "EMAIL_NOT_VERIFIED"
    assert _login(db_client)["email_verify_pending"] is False


def test_member_of_unverified_company_is_also_blocked(db_client, db_session, mailbox):
    """未验证的负责人另建成员也绕不过去（按企业判定）"""
    _signup(db_client, email="boss2@acme-d21.cn")
    owner = {"Authorization": f"Bearer {_login(db_client, 'boss2@acme-d21.cn')['access_token']}"}
    created = db_client.post("/api/v1/members", headers=owner, json={
        "username": "helper", "email": "helper@acme-d21.cn", "password": "Passw0rd!", "tenant_role": "operator",
    })
    assert created.status_code in (200, 201), created.text
    helper = {"Authorization": f"Bearer {_login(db_client, 'helper@acme-d21.cn')['access_token']}"}
    blocked = db_client.post(PLANS, headers=helper, json={"target_url": "https://example.com/list"})
    assert blocked.json()["code"] == "EMAIL_NOT_VERIFIED"


def test_bad_or_tampered_token_rejected(db_client, db_session, mailbox):
    _signup(db_client, email="boss3@acme-d21.cn")
    token = _token_from(mailbox[0][2])
    assert db_client.post(VERIFY, json={"token": token[:-3] + "abc"}).status_code == 400
    assert db_client.post(VERIFY, json={"token": "not-a-token-at-all-xxxx"}).status_code == 400


def test_resend_is_rate_limited(db_client, db_session, mailbox):
    _signup(db_client, email="boss4@acme-d21.cn")
    headers = {"Authorization": f"Bearer {_login(db_client, 'boss4@acme-d21.cn')['access_token']}"}
    assert db_client.post(RESEND, headers=headers).status_code == 200
    assert db_client.post(RESEND, headers=headers).status_code == 429
    assert len(mailbox) == 2  # 注册那封 + 第一次重发


def test_existing_accounts_are_not_pending(db_client, db_session, mailbox):
    """存量账号、负责人新建的成员不要求验证（迁移回填；pending 只在自助注册时置上）"""
    from conftest import make_tenant_owner_headers

    owner, _tid = make_tenant_owner_headers(db_session, slug="d21-legacy")

    async def _pending():
        async with db_session() as s:
            return (await s.execute(select(User.email_verify_pending).where(User.username == "owner-d21-legacy"))).scalar_one()

    assert asyncio.run(_pending()) in (0, False)
