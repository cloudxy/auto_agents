"""中转上线闸（审计 BUG-28 / B2-1 / F3-9，D19 = 卖）回归

用假网关（替换 llm_gateway.admin 的 generate/delete/block/unblock/观察函数）断言：
- SKU 账期已过读时即判 expired，签发被拒
- 吊销不受 SKU 状态限制（止损）
- 渠道组停用 / 启用 → 网关封 / 解封组内令牌；网关失败则组状态不变
- 令牌额度用尽 → 网关封禁，状态 exhausted
- 执法巡检：到期落库 + 封禁；续费后解封
- 企业月度中转额度用尽 → 拒绝签发 + 巡检封禁
- 日粒度用量只增不减
- 租户用量看板只给 token（无成本字段），中转单独计量
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from backend.services.llm_gateway import admin as gateway_admin
from backend.tests.relay_sku_support import seed_relay_sku
from conftest import make_tenant_owner_headers
from platform_core.models.relay import RelayGroup, RelayToken, RelayUsageDaily
from platform_core.models.relay_sku_entitlement import RelaySkuEntitlement
from platform_core.models.tenant import Tenant

GROUPS = "/api/v1/relay/groups"
TOKENS = "/api/v1/relay/tokens"
SKU = "/api/v1/relay/sku"


class FakeGateway:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.fail_block = False
        self.usage: dict[str, tuple[int, dict]] = {}
        self._n = 0

    async def generate_key(self, body, **_kw):
        self._n += 1
        self.calls.append(("generate", body.get("key_alias", "")))
        return {"key": f"sk-fake-{self._n:04d}-{'x' * 24}"}

    async def delete_key(self, body, **_kw):
        self.calls.append(("delete", ",".join(body.get("key_aliases") or [])))
        return {"deleted": True}

    async def block_key(self, key_hash, **_kw):
        if self.fail_block:
            raise httpx.ConnectError("gateway down")
        self.calls.append(("block", key_hash))
        return {}

    async def unblock_key(self, key_hash, **_kw):
        self.calls.append(("unblock", key_hash))
        return {}


@pytest.fixture
def gw(monkeypatch):
    fake = FakeGateway()
    for name in ("generate_key", "delete_key", "block_key", "unblock_key"):
        monkeypatch.setattr(gateway_admin, name, getattr(fake, name))
    return fake


def _run(coro):
    return asyncio.run(coro)


def _setup(db_client, db_session, slug: str, *, quota_tokens: int = -1):
    owner, tid = make_tenant_owner_headers(db_session, slug=slug)
    seed_relay_sku(db_session, tid, "active",
                   period_end=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=10))
    gid = db_client.post(GROUPS, headers=owner, json={"name": f"g-{slug}"}).json()["data"]["id"]
    resp = db_client.post(TOKENS, headers=owner,
                          json={"group_id": gid, "name": "t1", "quota_tokens": quota_tokens})
    assert resp.status_code in (200, 201), resp.text
    return owner, tid, gid, int(resp.json()["data"]["id"])


def _token(db_session, token_id: int) -> RelayToken:
    async def _go():
        async with db_session() as s:
            return await s.get(RelayToken, token_id)
    return _run(_go())


def test_sku_past_period_end_reads_expired_and_blocks_issue(db_client, db_session, gw):
    owner, tid = make_tenant_owner_headers(db_session, slug="re-exp")
    seed_relay_sku(db_session, tid, "active",
                   period_end=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1))
    page = db_client.get(SKU, headers=owner).json()["data"]
    assert page["status"] == "expired"  # 原先只读 status 列，付一次永久有效
    resp = db_client.post(GROUPS, headers=owner, json={"name": "g"})
    assert resp.status_code == 422 and resp.json()["code"] == "RELAY_SKU_INACTIVE"


def test_revoke_allowed_after_sku_expired(db_client, db_session, gw):
    owner, tid, gid, token_id = _setup(db_client, db_session, "re-revoke")
    seed_relay_sku(db_session, tid, "expired",
                   period_end=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1))
    resp = db_client.delete(f"{TOKENS}/{token_id}", headers=owner)
    assert resp.status_code == 200, resp.text  # 原先 422：到期后泄露的 key 吊销不了
    assert any(c[0] == "delete" for c in gw.calls)
    assert _token(db_session, token_id).revoked_at is not None


def test_group_disable_blocks_and_enable_unblocks_on_gateway(db_client, db_session, gw):
    owner, tid, gid, token_id = _setup(db_client, db_session, "re-group")
    key_hash = _token(db_session, token_id).key_hash
    off = db_client.patch(f"{GROUPS}/{gid}", headers=owner, json={"status": "disabled"})
    assert off.status_code == 200, off.text
    assert ("block", key_hash) in gw.calls
    row = _token(db_session, token_id)
    assert row.blocked_reason == "group_disabled"
    listed = db_client.get(TOKENS, headers=owner).json()["data"]
    assert [t["status"] for t in listed] == ["suspended"]
    on = db_client.patch(f"{GROUPS}/{gid}", headers=owner, json={"status": "enabled"})
    assert on.status_code == 200
    assert ("unblock", key_hash) in gw.calls
    assert _token(db_session, token_id).blocked_reason is None


def test_group_disable_gateway_failure_keeps_group_enabled(db_client, db_session, gw):
    owner, tid, gid, token_id = _setup(db_client, db_session, "re-group-fail")
    gw.fail_block = True
    resp = db_client.patch(f"{GROUPS}/{gid}", headers=owner, json={"status": "disabled"})
    assert resp.status_code == 502
    assert resp.json()["code"] == "RELAY_GATEWAY_UNAVAILABLE"

    async def _status():
        async with db_session() as s:
            return (await s.get(RelayGroup, gid)).status

    assert _run(_status()) == "enabled"  # 不出现「本地停用、网关照跑」的假停用


def test_token_quota_exhausted_blocks_on_observation(db_client, db_session, gw, monkeypatch):
    from backend.services.relay_service import RelayService

    owner, tid, gid, token_id = _setup(db_client, db_session, "re-quota", quota_tokens=100)

    async def _obs(self, row):
        return 150, datetime(2026, 9, 28, 1, 0), {date(2026, 9, 28): 150}

    monkeypatch.setattr(RelayService, "_observe_gateway_usage", _obs)
    detail = db_client.get(f"{TOKENS}/{token_id}", headers=owner)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["status"] == "exhausted"
    row = _token(db_session, token_id)
    assert row.blocked_reason == "quota_exhausted"
    assert ("block", row.key_hash) in gw.calls  # 原先额度只在本地展示，网关照放


def test_daily_usage_is_monotonic(db_client, db_session, gw, monkeypatch):
    from backend.services.relay_service import RelayService

    owner, tid, gid, token_id = _setup(db_client, db_session, "re-mono")
    seq = iter([
        (80, None, {date(2026, 9, 27): 30, date(2026, 9, 28): 50}),
        (20, None, {date(2026, 9, 28): 20}),  # 网关分页截断 / 日志清理：观察值变小
    ])

    async def _obs(self, row):
        return next(seq)

    monkeypatch.setattr(RelayService, "_observe_gateway_usage", _obs)
    assert db_client.get(f"{TOKENS}/{token_id}", headers=owner).json()["data"]["used_tokens"] == 80
    assert db_client.get(f"{TOKENS}/{token_id}", headers=owner).json()["data"]["used_tokens"] == 80

    async def _facts():
        async with db_session() as s:
            rows = (await s.execute(select(RelayUsageDaily).where(
                RelayUsageDaily.token_id == token_id))).scalars().all()
            return {r.stat_date: int(r.total_tokens) for r in rows}

    assert _run(_facts()) == {date(2026, 9, 27): 30, date(2026, 9, 28): 50}


def test_patrol_expires_sku_blocks_then_renewal_unblocks(db_client, db_session, gw):
    from backend.services.billing_fulfill import activate_relay_sku
    from backend.services.relay_enforcement import RelayEnforcementService

    owner, tid, gid, token_id = _setup(db_client, db_session, "re-patrol")
    seed_relay_sku(db_session, tid, "active",
                   period_end=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5))

    async def _patrol():
        async with db_session() as s:
            return await RelayEnforcementService().run_once(s)

    stats = _run(_patrol())
    assert stats["sku_expired"] == 1 and stats["blocked"] == 1
    row = _token(db_session, token_id)
    assert row.blocked_reason == "sku_expired"

    async def _sku():
        async with db_session() as s:
            return (await s.execute(select(RelaySkuEntitlement).where(
                RelaySkuEntitlement.tenant_id == tid))).scalar_one().status

    assert _run(_sku()) == "expired"

    async def _renew():
        async with db_session() as s:
            await activate_relay_sku(s, tid, datetime.now(timezone.utc))
            await s.commit()

    _run(_renew())
    assert _token(db_session, token_id).blocked_reason is None
    assert ("unblock", row.key_hash) in gw.calls


def test_tenant_monthly_relay_quota(db_client, db_session, gw):
    from backend.services.quota_service import shanghai_year_month
    from backend.services.relay_enforcement import RelayEnforcementService

    owner, tid, gid, token_id = _setup(db_client, db_session, "re-tenant")
    year, month = (int(x) for x in shanghai_year_month().split("-"))

    async def _seed():
        async with db_session() as s:
            t = await s.get(Tenant, tid)
            t.quota = {**(t.quota or {}), "relay_tokens_month": 1000}
            s.add(RelayUsageDaily(tenant_id=tid, token_id=token_id,
                                  stat_date=date(year, month, 1), total_tokens=1200))
            await s.commit()

    _run(_seed())
    resp = db_client.post(TOKENS, headers=owner, json={"group_id": gid, "name": "t2"})
    assert resp.status_code == 422 and resp.json()["code"] == "RELAY_TENANT_QUOTA_EXHAUSTED"

    async def _patrol():
        async with db_session() as s:
            return await RelayEnforcementService().run_once(s)

    _run(_patrol())
    assert _token(db_session, token_id).blocked_reason == "tenant_quota"

    usage = db_client.get("/api/v1/tenants/me/usage", headers=owner).json()["data"]
    assert usage["relay"] == {"sku_status": "active", "used_tokens": 1200, "limit_tokens": 1000}
    assert "cost_cents_total" not in usage and "cost_by_provider" not in usage  # D19：只给 token
