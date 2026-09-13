"""T-18 FR-U20/U21/U22/U23：我的渠道组闸在 relay_sku_entitlements，不 COUNT 组行。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

from sqlalchemy import func, select

from backend.tests.relay_sku_support import seed_relay_sku
from conftest import make_tenant_owner_headers
from platform_core.models.billing import Order
from platform_core.models.relay import RelayGroup, RelayToken
from platform_core.models.relay_sku_entitlement import RelaySkuEntitlement

GROUPS = "/api/v1/relay/groups"
TOKENS = "/api/v1/relay/tokens"
SKU = "/api/v1/relay/sku"
BY_KEY = "/api/v1/relay/tokens/by-key"
NEWAPI = "/api/v1/newapi/overview"
NEWAPI_CFG = "/api/v1/newapi/channels/3/config"
GHOST = "/api/v1/admin/tenants"
SORRY = "抱歉您没有权限"
MSG_NONE = "未开通中转"
MSG_EXPIRED = "中转已到期"
MSG_TOKENS_EMPTY = "还没有令牌"
MSG_CANNOT_ISSUE = "当前账号不能签发，请联系企业管理员"
BUYABLE = "当前可买"


def _member_headers(db_session, tid: int, tenant_role: str, username: str) -> dict:
    from backend.services.auth_service import AuthService
    from platform_core.models.user import User

    async def _go():
        async with db_session() as s:
            s.add(User(
                username=username, email=f"{username}@x.co", password_hash="x",
                role=tenant_role, tenant_id=tid, tenant_role=tenant_role, is_active=True,
            ))
            await s.commit()
            u = (await s.execute(select(User).where(User.username == username))).scalar_one()
            token = await AuthService(s).create_token({
                "id": u.id, "username": u.username, "is_admin": False, "role": tenant_role,
                "tenant_id": tid, "tenant_role": tenant_role, "is_platform_admin": False,
            })
            return token.access_token

    return {"Authorization": f"Bearer {asyncio.run(_go())}"}


def _assert_missing_shape(resp, ghost):
    assert resp.status_code == ghost.status_code == 404, resp.text
    body, other = resp.json(), ghost.json()
    assert body["code"] == other["code"] == "HTTP_404"
    assert body["message"] == other["message"] == "Not Found"
    assert SORRY not in resp.text
    assert "抱歉" not in resp.text


def _token_count(db_session, tid: int) -> int:
    async def _go():
        async with db_session() as s:
            return int((await s.execute(
                select(func.count()).select_from(RelayToken).where(
                    RelayToken.tenant_id == tid,
                )
            )).scalar_one())

    return asyncio.run(_go())


def _insert_group(db_session, tid: int, name: str = "骨架组") -> int:
    async def _go():
        async with db_session() as s:
            row = RelayGroup(tenant_id=tid, name=name)
            s.add(row)
            await s.commit()
            await s.refresh(row)
            return int(row.id)

    return asyncio.run(_go())


def _insert_token(db_session, tid: int, gid: int, *, name: str = "seed") -> int:
    async def _go():
        async with db_session() as s:
            row = RelayToken(
                tenant_id=tid, group_id=gid, name=name,
                key_prefix="sk-seedxxxx", key_hash=f"h-{name}-{tid}",
                quota_tokens=-1,
            )
            s.add(row)
            await s.commit()
            await s.refresh(row)
            return int(row.id)

    return asyncio.run(_go())


def _blob(*paths: str) -> str:
    return "\n".join(Path(p).read_text(encoding="utf-8") for p in paths)


def test_gwt_u21_1_missing_row_empty_copy_upgrade_relay(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="u21-miss")
    _insert_group(db_session, tid)
    groups = db_client.get(GROUPS, headers=owner)
    assert groups.status_code == 200, groups.text
    assert groups.json()["data"] == []
    assert MSG_NONE in groups.json()["message"]
    tokens = db_client.get(TOKENS, headers=owner)
    assert tokens.json()["data"] == []
    assert MSG_NONE in tokens.json()["message"]
    page = db_client.get(SKU, headers=owner)
    assert page.status_code == 200, page.text
    data = page.json()["data"]
    assert data["status"] == "none"
    assert data["can_issue"] is False
    assert data["empty_title"] == MSG_NONE
    assert data["upgrade"]["product"] == "relay"
    assert data["upgrade"]["action"] == "checkout"
    assert data["upgrade"]["checkout_path"] == "/billing/checkout?product=relay"
    assert data["upgrade"]["message"] == "去升级"
    assert BUYABLE not in page.text
    assert "已开通" not in page.text
    assert "使用中" not in page.text


def test_gwt_u21_1_status_none_row_same_as_missing(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="u21-none")
    seed_relay_sku(db_session, tid, "none")
    _insert_group(db_session, tid)
    groups = db_client.get(GROUPS, headers=owner)
    assert groups.json()["data"] == []
    assert MSG_NONE in groups.json()["message"]


def test_gwt_u21_2_nav_has_no_subscribed_badge(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="u21-badge")
    op = _member_headers(db_session, tid, "operator", "u21-op")
    page = db_client.get(SKU, headers=op)
    assert page.json()["data"]["status"] == "none"
    assert "已开通" not in page.text
    assert "使用中" not in page.text
    assert BUYABLE not in page.text


def test_gwt_u21_3_issue_refused_when_inactive(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="u21-issue")
    gid = _insert_group(db_session, tid)
    before = _token_count(db_session, tid)
    resp = db_client.post(TOKENS, headers=owner, json={"group_id": gid, "name": "x"})
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "RELAY_SKU_INACTIVE"
    assert MSG_NONE in resp.json()["message"]
    assert _token_count(db_session, tid) == before == 0
    op = _member_headers(db_session, tid, "operator", "u21-op-iss")
    again = db_client.post(TOKENS, headers=op, json={"group_id": gid, "name": "y"})
    assert again.status_code == 422
    assert _token_count(db_session, tid) == 0


def test_gwt_u20_1_active_lists_own_groups_no_upstream_key(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="u20-list")
    seed_relay_sku(db_session, tid)
    created = db_client.post(
        GROUPS, headers=owner,
        json={"name": "vip", "rpm_limit": 10, "models": ["gpt-4o"]},
    )
    assert created.status_code == 201, created.text
    listed = db_client.get(GROUPS, headers=owner)
    assert listed.status_code == 200
    rows = listed.json()["data"]
    assert len(rows) == 1
    assert rows[0]["name"] == "vip"
    blob = listed.text.lower()
    assert "sk-" not in blob
    assert "api_key" not in blob
    assert "master" not in blob
    page = db_client.get(SKU, headers=owner)
    assert page.json()["data"]["status"] == "active"
    assert page.json()["data"]["can_issue"] is True
    assert page.json()["data"]["upgrade"] is None
    assert NEWAPI.split("/overview")[0] not in listed.text


def test_gwt_u20_2_active_zero_tokens_empty_copy(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="u20-empty")
    seed_relay_sku(db_session, tid)
    tokens = db_client.get(TOKENS, headers=owner)
    assert tokens.status_code == 200
    assert tokens.json()["data"] == []
    assert MSG_TOKENS_EMPTY in tokens.json()["message"]
    assert tokens.status_code != 500


def test_gwt_u20_3_cross_tenant_404_same_shape(db_client, db_session, monkeypatch):
    from backend.services.llm_gateway import admin as gateway_admin

    owner_a, tid_a = make_tenant_owner_headers(db_session, slug="u20-a")
    owner_b, _tid_b = make_tenant_owner_headers(db_session, slug="u20-b")
    seed_relay_sku(db_session, tid_a)
    seed_relay_sku(db_session, _tid_b)
    created = db_client.post(GROUPS, headers=owner_a, json={"name": "a-only"})
    gid = created.json()["data"]["id"]

    async def _fake_generate(body, **_kwargs):
        return {"key": "sk-plain-u20", "token_id": "tok-u20"}

    monkeypatch.setattr(gateway_admin, "generate_key", _fake_generate)
    issued = db_client.post(TOKENS, headers=owner_a, json={"group_id": gid, "name": "ci"})
    assert issued.status_code == 201, issued.text
    token_id = issued.json()["data"]["id"]
    ghost = db_client.get(GHOST, headers=owner_b)
    stolen_g = db_client.patch(
        f"{GROUPS}/{gid}", headers=owner_b, json={"status": "disabled"},
    )
    _assert_missing_shape(stolen_g, ghost)
    stolen_t = db_client.get(f"{TOKENS}/{token_id}", headers=owner_b)
    _assert_missing_shape(stolen_t, ghost)
    listed_b = db_client.get(GROUPS, headers=owner_b)
    assert listed_b.json()["data"] == []
    assert all(r.get("name") != "a-only" for r in listed_b.json()["data"])


def test_gwt_u22_duty_page_404_even_when_sku_active(db_client, db_session, monkeypatch):
    owner, tid = make_tenant_owner_headers(db_session, slug="u22-duty")
    seed_relay_sku(db_session, tid)
    ghost = db_client.get(GHOST, headers=owner)
    overview = db_client.get(NEWAPI, headers=owner)
    _assert_missing_shape(overview, ghost)
    spy = AsyncMock()
    monkeypatch.setattr(
        "backend.services.channel_config_service.ChannelConfigService.set_config", spy,
    )
    cfg = db_client.put(NEWAPI_CFG, headers=owner, json={
        "limit_quota": 10, "window_hours": 24, "cooldown_seconds": 60,
    })
    _assert_missing_shape(cfg, ghost)
    spy.assert_not_awaited()
    page = db_client.get(SKU, headers=owner)
    assert "litellm" not in page.text.lower()
    assert "改全局熔断" not in page.text
    assert "/v1/chat" not in page.text


def test_gwt_u23_1_plaintext_once_later_prefix_only(
    db_client, db_session, monkeypatch,
):
    from backend.services.llm_gateway import admin as gateway_admin

    owner, tid = make_tenant_owner_headers(db_session, slug="u23-once")
    seed_relay_sku(db_session, tid)
    gid = db_client.post(GROUPS, headers=owner, json={"name": "g"}).json()["data"]["id"]

    async def _fake_generate(body, **_kwargs):
        return {"key": "sk-once-only-plain", "token_id": "tok-once"}

    monkeypatch.setattr(gateway_admin, "generate_key", _fake_generate)
    issued = db_client.post(TOKENS, headers=owner, json={"group_id": gid, "name": "ci"})
    assert issued.status_code == 201, issued.text
    assert issued.json()["data"]["plaintext_key"] == "sk-once-only-plain"
    token_id = issued.json()["data"]["id"]
    listed = db_client.get(TOKENS, headers=owner)
    row = listed.json()["data"][0]
    assert row["plaintext_key"] is None
    assert row["key_prefix"].startswith("sk-once")
    assert "sk-once-only-plain" not in listed.text
    detail = db_client.get(f"{TOKENS}/{token_id}", headers=owner)
    assert detail.json()["data"]["plaintext_key"] is None
    assert "sk-once-only-plain" not in detail.text


def test_gwt_u23_2_revoked_only_shows_empty_tokens(
    db_client, db_session, monkeypatch,
):
    from backend.services.llm_gateway import admin as gateway_admin

    owner, tid = make_tenant_owner_headers(db_session, slug="u23-rev")
    seed_relay_sku(db_session, tid)
    gid = db_client.post(GROUPS, headers=owner, json={"name": "g"}).json()["data"]["id"]

    async def _fake_generate(body, **_kwargs):
        return {"key": "sk-rev-plain-1", "token_id": "tok-rev"}

    async def _fake_delete(body, **_kwargs):
        return {"deleted_keys": [], "key_aliases": {}}

    monkeypatch.setattr(gateway_admin, "generate_key", _fake_generate)
    monkeypatch.setattr(gateway_admin, "delete_key", _fake_delete)
    issued = db_client.post(TOKENS, headers=owner, json={"group_id": gid, "name": "ci"})
    token_id = issued.json()["data"]["id"]
    raw = issued.json()["data"]["plaintext_key"]
    revoked = db_client.delete(f"{TOKENS}/{token_id}", headers=owner)
    assert revoked.status_code == 200
    listed = db_client.get(TOKENS, headers=owner)
    assert listed.json()["data"] == []
    assert MSG_TOKENS_EMPTY in listed.json()["message"]
    ghost = db_client.get(GHOST, headers=owner)
    by_key = db_client.get(BY_KEY, headers={**owner, "X-Relay-Token": raw})
    _assert_missing_shape(by_key, ghost)


def test_gwt_u23_4_expired_sku_issue_copy(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="u23-exp")
    seed_relay_sku(
        db_session, tid, "expired",
        period_end=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1),
    )
    gid = _insert_group(db_session, tid)
    _insert_token(db_session, tid, gid, name="old")
    groups = db_client.get(GROUPS, headers=owner)
    assert groups.json()["data"] == []
    assert MSG_EXPIRED in groups.json()["message"]
    tokens = db_client.get(TOKENS, headers=owner)
    assert tokens.json()["data"] == []
    assert MSG_EXPIRED in tokens.json()["message"]
    page = db_client.get(SKU, headers=owner)
    assert page.json()["data"]["status"] == "expired"
    assert page.json()["data"]["upgrade"]["product"] == "relay"
    issued = db_client.post(TOKENS, headers=owner, json={"group_id": gid, "name": "new"})
    assert issued.status_code == 422
    assert issued.json()["code"] == "RELAY_SKU_INACTIVE"
    assert MSG_EXPIRED in issued.json()["message"]
    assert _token_count(db_session, tid) == 1


def test_gwt_u23_5_operator_cannot_issue_when_active(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="u23-op")
    seed_relay_sku(db_session, tid)
    gid = db_client.post(GROUPS, headers=owner, json={"name": "g"}).json()["data"]["id"]
    op = _member_headers(db_session, tid, "operator", "u23-operator")
    before = _token_count(db_session, tid)
    resp = db_client.post(TOKENS, headers=op, json={"group_id": gid, "name": "x"})
    assert resp.status_code != 403
    assert MSG_CANNOT_ISSUE in resp.json()["message"]
    assert _token_count(db_session, tid) == before
    assert "plaintext_key" not in (resp.json().get("data") or {}) or resp.json()["data"] is None


def test_gwt_u23_3_6_7_token_as_credential(
    db_client, db_session, monkeypatch,
):
    from backend.services.llm_gateway import admin as gateway_admin

    owner_a, tid_a = make_tenant_owner_headers(db_session, slug="u23-ta")
    owner_b, tid_b = make_tenant_owner_headers(db_session, slug="u23-tb")
    seed_relay_sku(db_session, tid_a)
    seed_relay_sku(db_session, tid_b)
    gid_a = db_client.post(GROUPS, headers=owner_a, json={"name": "ga"}).json()["data"]["id"]
    gid_b = db_client.post(GROUPS, headers=owner_b, json={"name": "gb"}).json()["data"]["id"]
    n = {"n": 0}

    async def _fake_generate(body, **_kwargs):
        n["n"] += 1
        return {"key": f"sk-cred-{n['n']}", "token_id": f"tok-{n['n']}"}

    monkeypatch.setattr(gateway_admin, "generate_key", _fake_generate)
    issued_a = db_client.post(TOKENS, headers=owner_a, json={"group_id": gid_a, "name": "a"})
    issued_b = db_client.post(TOKENS, headers=owner_b, json={"group_id": gid_b, "name": "b"})
    raw_a = issued_a.json()["data"]["plaintext_key"]
    raw_b = issued_b.json()["data"]["plaintext_key"]
    mine = db_client.get(BY_KEY, headers={**owner_a, "X-Relay-Token": raw_a})
    assert mine.status_code == 200, mine.text
    assert mine.json()["data"]["plaintext_key"] is None
    assert mine.json()["data"]["key_prefix"].startswith("sk-cred")
    ghost_b = db_client.get(GHOST, headers=owner_b)
    cross = db_client.get(BY_KEY, headers={**owner_b, "X-Relay-Token": raw_a})
    _assert_missing_shape(cross, ghost_b)
    assert mine.json()["data"]["id"] != issued_b.json()["data"]["id"]
    seed_relay_sku(db_session, tid_a, "expired")
    expired = db_client.get(BY_KEY, headers={**owner_a, "X-Relay-Token": raw_a})
    ghost_a = db_client.get(GHOST, headers=owner_a)
    _assert_missing_shape(expired, ghost_a)
    still_b = db_client.get(BY_KEY, headers={**owner_b, "X-Relay-Token": raw_b})
    assert still_b.status_code == 200


def test_plan_pro_order_does_not_open_relay(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="u33-pro")
    _insert_group(db_session, tid)

    async def _go():
        async with db_session() as s:
            s.add(Order(
                tenant_id=tid, amount_cents=29900, status="fulfilled",
                channel="offline", product_code="plan_pro", order_no="pro-u33",
            ))
            await s.commit()

    asyncio.run(_go())
    groups = db_client.get(GROUPS, headers=owner)
    assert groups.json()["data"] == []
    assert MSG_NONE in groups.json()["message"]
    page = db_client.get(SKU, headers=owner)
    assert page.json()["data"]["status"] == "none"

    async def _sku_rows():
        async with db_session() as s:
            return list((await s.execute(
                select(RelaySkuEntitlement).where(RelaySkuEntitlement.tenant_id == tid)
            )).scalars().all())

    assert asyncio.run(_sku_rows()) == []


def test_relay_modules_only_read_entitlement():
    blob = _blob(
        "backend/services/relay_service.py",
        "backend/services/relay_sku_gate.py",
        "backend/repositories/relay_sku_entitlement_repository.py",
        "backend/app/api/v1/relay.py",
    )
    assert "RelaySkuEntitlement(" not in blob
    assert "func.count" not in blob
    assert "payment_provider" not in blob
    assert "alipay" not in blob.lower()
    assert BUYABLE not in blob
