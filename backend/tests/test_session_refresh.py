"""会话续期（决策 D10 = A，2026-09-29「按照建议做」）

原状：访问令牌 30 分钟、没有 refresh，客户每干 30 分钟活就被踢回登录页。
约定：
- 登录同时下发 refresh 令牌：勾「记住我」7 天，不勾 12 小时；绝对上限 30 天
- 刷新即轮换；同一 refresh 令牌宽限期（多标签页并发）外被重复使用 = 疑似被盗，
  吊销该用户全部会话（token_version +1）
- refresh 令牌不能当访问令牌用；登出吊销本会话 refresh；改密 / 停用后 refresh 失效
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select

from conftest import make_tenant_owner_headers
from platform_core.models.user import User
from stubs import FakeRedis

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
PERMS = "/api/v1/auth/permissions"


@pytest.fixture
def fake_redis(monkeypatch):
    import backend.services.session_service as svc

    redis = FakeRedis()
    monkeypatch.setattr(svc, "get_async_redis", lambda: redis)
    return redis


def _user(db_session, username: str, password: str = "Passw0rd!"):
    from backend.utils.auth import get_password_hash

    _owner, tid = make_tenant_owner_headers(db_session, slug=f"s-{username}")

    async def _go():
        async with db_session() as s:
            s.add(User(username=username, email=f"{username}@x.co", password_hash=get_password_hash(password),
                       role="operator", tenant_id=tid, tenant_role="operator", is_active=True))
            await s.commit()
            return int((await s.execute(select(User.id).where(User.username == username))).scalar_one())

    return asyncio.run(_go())


def _login(client, username, remember=False, password="Passw0rd!"):
    resp = client.post(LOGIN, json={"username": username, "password": password, "remember_me": remember})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _claims(token):
    from backend.utils.auth import decode_token_any

    return decode_token_any(token)


def test_login_issues_refresh_token_with_remember_window(db_client, db_session, fake_redis):
    _user(db_session, "rf-remember")
    remembered = _login(db_client, "rf-remember", remember=True)
    session_only = _login(db_client, "rf-remember", remember=False)
    assert remembered["refresh_token"] and remembered["expires_in"] == 30 * 60
    r1, r2 = _claims(remembered["refresh_token"]), _claims(session_only["refresh_token"])
    assert r1["typ"] == "refresh" and r2["typ"] == "refresh"
    assert timedelta(seconds=r1["exp"] - r1["iat"]) == timedelta(days=7)
    assert timedelta(seconds=r2["exp"] - r2["iat"]) == timedelta(hours=12)


def test_refresh_token_is_not_an_access_token(db_client, db_session, fake_redis):
    _user(db_session, "rf-notaccess")
    data = _login(db_client, "rf-notaccess")
    assert db_client.get(PERMS, headers=_bearer(data["refresh_token"])).status_code == 401
    # 只差 typ 一个字段的令牌也必须被拒（否则 7 天的刷新令牌等于 7 天的访问令牌）
    from backend.utils.auth import create_access_token

    access = _claims(data["access_token"])
    forged = create_access_token({k: v for k, v in access.items() if k not in ("exp", "iat")} | {"typ": "refresh"})
    assert db_client.get(PERMS, headers=_bearer(forged)).status_code == 401
    same_but_access = create_access_token({k: v for k, v in access.items() if k not in ("exp", "iat", "typ")})
    assert db_client.get(PERMS, headers=_bearer(same_but_access)).status_code == 200


def test_refresh_rotates_and_new_access_works(db_client, db_session, fake_redis):
    _user(db_session, "rf-rotate")
    data = _login(db_client, "rf-rotate", remember=True)
    resp = db_client.post(REFRESH, json={"refresh_token": data["refresh_token"]})
    assert resp.status_code == 200, resp.text
    new = resp.json()["data"]
    assert new["refresh_token"] != data["refresh_token"]
    assert db_client.get(PERMS, headers=_bearer(new["access_token"])).status_code == 200
    # 轮换后仍保留「记住我」窗口
    assert _claims(new["refresh_token"])["rm"] is True


def test_reuse_within_grace_is_tolerated(db_client, db_session, fake_redis):
    """两个标签页同时拿同一个 refresh 令牌去换：都成功，不算被盗"""
    _user(db_session, "rf-tabs")
    data = _login(db_client, "rf-tabs")
    first = db_client.post(REFRESH, json={"refresh_token": data["refresh_token"]})
    second = db_client.post(REFRESH, json={"refresh_token": data["refresh_token"]})
    assert first.status_code == 200 and second.status_code == 200


def test_reuse_after_grace_revokes_all_sessions(db_client, db_session, fake_redis, monkeypatch):
    import backend.services.session_service as svc

    _user(db_session, "rf-stolen")
    data = _login(db_client, "rf-stolen")
    rotated = db_client.post(REFRESH, json={"refresh_token": data["refresh_token"]}).json()["data"]
    monkeypatch.setattr(svc, "_now_ts", lambda: svc.time.time() + 3600)  # 宽限期早已过去
    replay = db_client.post(REFRESH, json={"refresh_token": data["refresh_token"]})
    assert replay.status_code == 401
    monkeypatch.undo()
    # 疑似被盗：该用户所有会话作废，包括刚轮换出的新令牌
    assert db_client.get(PERMS, headers=_bearer(rotated["access_token"])).status_code == 401
    assert db_client.post(REFRESH, json={"refresh_token": rotated["refresh_token"]}).status_code == 401


def test_logout_revokes_refresh(db_client, db_session, fake_redis):
    _user(db_session, "rf-logout")
    data = _login(db_client, "rf-logout")
    assert db_client.post(LOGOUT, json={"refresh_token": data["refresh_token"]}).status_code == 200
    assert db_client.post(REFRESH, json={"refresh_token": data["refresh_token"]}).status_code == 401


def test_logout_on_one_device_keeps_the_other(db_client, db_session, fake_redis):
    """登出只作废本会话，不株连其它设备（不能被当成「令牌被盗」吊销全部）"""
    _user(db_session, "rf-two-devices")
    phone = _login(db_client, "rf-two-devices")
    laptop = _login(db_client, "rf-two-devices")
    db_client.post(LOGOUT, json={"refresh_token": phone["refresh_token"]})
    db_client.post(REFRESH, json={"refresh_token": phone["refresh_token"]})  # 已登出的再用一次
    assert db_client.get(PERMS, headers=_bearer(laptop["access_token"])).status_code == 200
    assert db_client.post(REFRESH, json={"refresh_token": laptop["refresh_token"]}).status_code == 200


def test_refresh_rejected_after_password_reset_or_disable(db_client, db_session, fake_redis):
    uid = _user(db_session, "rf-reset")
    data = _login(db_client, "rf-reset")

    async def _bump():
        async with db_session() as s:
            user = await s.get(User, uid)
            user.token_version = int(user.token_version or 0) + 1
            await s.commit()

    asyncio.run(_bump())
    assert db_client.post(REFRESH, json={"refresh_token": data["refresh_token"]}).status_code == 401

    uid2 = _user(db_session, "rf-disabled")
    data2 = _login(db_client, "rf-disabled")

    async def _disable():
        async with db_session() as s:
            (await s.get(User, uid2)).is_active = False
            await s.commit()

    asyncio.run(_disable())
    assert db_client.post(REFRESH, json={"refresh_token": data2["refresh_token"]}).status_code == 401


def test_absolute_session_cap(db_client, db_session, fake_redis, monkeypatch):
    import backend.services.session_service as svc

    _user(db_session, "rf-cap")
    data = _login(db_client, "rf-cap", remember=True)
    monkeypatch.setattr(svc, "_now_ts", lambda: svc.time.time() + 31 * 86400)
    original = svc._decode_refresh
    monkeypatch.setattr(svc, "_decode_refresh", lambda token, verify_exp=True: original(token, verify_exp=False))
    assert db_client.post(REFRESH, json={"refresh_token": data["refresh_token"]}).status_code == 401


def test_access_token_ttl_still_short(db_client, db_session, fake_redis):
    _user(db_session, "rf-ttl")
    data = _login(db_client, "rf-ttl")
    c = _claims(data["access_token"])
    assert c.get("typ", "access") == "access"
    assert c["exp"] - c["iat"] == 30 * 60
