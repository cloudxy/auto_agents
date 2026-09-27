"""T-24 / FR-M51：注册=创建企业；名≥2；无个人空间。

GWT-M51.1 成功创建企业 / M51.2 空名 / M51.3 已登录无个人空间入口 / M51.4 一字名。
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from backend.services.auth_service import AuthService
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

SIGNUP_URL = "/api/v1/public/tenant/signup"
PERSONAL_PATHS = (
    "/api/v1/personal-space",
    "/api/v1/me/personal",
    "/api/v1/users/me/personal-space",
)


@pytest.fixture(autouse=True)
def _no_signup_rate_limit(monkeypatch):
    monkeypatch.setattr(
        "backend.app.api.v1.tenant_signup.enforce_request_limit",
        AsyncMock(return_value=None),
    )


def _tenant_count(db_session) -> int:
    import asyncio

    async def _go() -> int:
        async with db_session() as s:
            return int((await s.execute(select(func.count()).select_from(Tenant))).scalar_one())

    return asyncio.run(_go())


def test_gwt_m51_1_signup_creates_enterprise_not_personal_space(db_client, db_session):
    """GWT-M51.1：访客填企业名≥2 → 创建该企业；响应不是个人空间。"""
    resp = db_client.post(
        SIGNUP_URL,
        json={
            "company": "星云采集",
            "admin_email": "boss@xingyun.test",
            "admin_password": "SuperSecret1!",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["tenant"]["name"] == "星云采集"
    assert data["tenant"]["id"]
    assert data["owner"]["email"] == "boss@xingyun.test"
    assert "personal_space" not in data
    assert "personal" not in data
    login = db_client.post(
        "/api/v1/auth/login",
        json={"username": data["owner"]["username"], "password": "SuperSecret1!"},
    )
    assert login.status_code == 200, login.text

    async def _owner_tid() -> int:
        async with db_session() as s:
            u = (await s.execute(
                select(User).where(User.email == "boss@xingyun.test")
            )).scalar_one()
            return int(u.tenant_id)

    assert asyncio.run(_owner_tid()) == data["tenant"]["id"]


def test_gwt_m51_2_empty_company_copy_no_create(db_client, db_session):
    """GWT-M51.2：企业名为空 → 「请填写企业名」；不创建。"""
    before = _tenant_count(db_session)
    resp = db_client.post(
        SIGNUP_URL,
        json={"company": "", "admin_email": "empty@x.test", "admin_password": "SuperSecret1!"},
    )
    assert resp.status_code == 422, resp.text
    assert "请填写企业名" in resp.json()["message"]
    assert _tenant_count(db_session) == before
    login = db_client.post(
        "/api/v1/auth/login",
        json={"username": "empty", "password": "SuperSecret1!"},
    )
    assert login.status_code == 401


def test_gwt_m51_4_one_char_company_copy_no_create(db_client, db_session):
    """GWT-M51.4：企业名恰好 1 字 → 「企业名至少 2 个字符」；不创建。"""
    before = _tenant_count(db_session)
    resp = db_client.post(
        SIGNUP_URL,
        json={"company": "星", "admin_email": "one@x.test", "admin_password": "SuperSecret1!"},
    )
    assert resp.status_code == 422, resp.text
    assert "企业名至少 2 个字符" in resp.json()["message"]
    assert _tenant_count(db_session) == before


def test_gwt_m51_3_logged_in_operator_has_no_personal_space(db_client, db_session):
    """GWT-M51.3：已登录经办寻找个人空间入口 → 没有该入口。"""
    import asyncio

    from conftest import make_tenant_owner_headers

    _headers, tid = make_tenant_owner_headers(db_session, slug="m51-3")

    async def _op():
        async with db_session() as s:
            s.add(User(
                username="m51-3-op", email="m51-3-op@x.co", password_hash="x",
                role="operator", tenant_id=tid, tenant_role="operator", is_active=True,
            ))
            await s.commit()
            u = (await s.execute(select(User).where(User.username == "m51-3-op"))).scalar_one()
            token = await AuthService(s).create_token({
                "id": u.id, "username": u.username, "is_admin": False,
                "role": "operator", "tenant_id": tid, "tenant_role": "operator",
                "is_platform_admin": False,
            })
            return token.access_token

    op_headers = {"Authorization": f"Bearer {asyncio.run(_op())}"}
    before = _tenant_count(db_session)
    for path in PERSONAL_PATHS:
        resp = db_client.get(path, headers=op_headers)
        assert resp.status_code == 404, path
        assert "个人空间" not in resp.text
    signup = db_client.post(
        SIGNUP_URL, headers=op_headers,
        json={
            "company": "个人空间",
            "admin_email": "solo@x.test",
            "admin_password": "SuperSecret1!",
        },
    )
    assert signup.status_code == 422
    assert _tenant_count(db_session) == before
