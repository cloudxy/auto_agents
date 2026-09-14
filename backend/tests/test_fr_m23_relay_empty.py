"""T-16 / FR-M23：未开通 vs 已开通零令牌；专业档仍未开通。"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.billing import Plan

SKU = "/api/v1/relay/sku"
TOKENS = "/api/v1/relay/tokens"
GROUPS = "/api/v1/relay/groups"
CHECKOUT = "/api/v1/billing/checkout"
CONFIRM = "/api/v1/billing/orders/{id}/confirm"
MSG_NONE = "未开通中转"
MSG_TOKENS = "还没有令牌"
BUYABLE = "当前可买"


def _seed_plans(db_session) -> None:
    async def _go():
        async with db_session() as s:
            if (await s.execute(select(Plan).where(Plan.slug == "pro"))).scalar_one_or_none():
                return
            s.add_all([
                Plan(
                    slug="pro", name="专业档", price_cents=29900, period="month",
                    quota_json='{"task_concurrency":20,"result_storage":500000,"llm_tokens_month":5000000}',
                    is_public=1,
                ),
                Plan(
                    slug="enterprise", name="企业档", price_cents=99900, period="month",
                    quota_json='{"task_concurrency":50,"result_storage":2000000,"llm_tokens_month":20000000}',
                    is_public=1,
                ),
            ])
            await s.commit()

    asyncio.run(_go())


def _confirm(db_client, db_session, slug: str, product: str, monkeypatch=None):
    if product == "relay" and monkeypatch is not None:
        import backend.services.billing_service as billing_mod
        orig = billing_mod.settings.get

        def _get(key, default=None):
            if key == "BILLING.RELAY_PRICE_CENTS":
                return 19900
            return orig(key, default)

        monkeypatch.setattr(billing_mod.settings, "get", _get)
    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug=slug)
    pa = make_platform_admin_headers(db_session)
    created = db_client.post(CHECKOUT, headers=owner, json={"product": product})
    assert created.status_code == 201, created.text
    oid = created.json()["data"]["id"]
    resp = db_client.post(CONFIRM.format(id=oid), headers=pa)
    assert resp.status_code == 200, resp.text
    return owner, tid


def test_gwt_m23_2_unopened_copy_not_token_empty(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="m23-2")
    page = db_client.get(SKU, headers=owner)
    assert page.status_code == 200, page.text
    assert MSG_NONE in page.json()["message"] or page.json()["data"]["empty_title"] == MSG_NONE
    assert MSG_TOKENS not in page.text
    assert "已开通" not in page.text
    assert "使用中" not in page.text
    assert BUYABLE not in page.text
    tokens = db_client.get(TOKENS, headers=owner)
    assert tokens.json()["data"] == []
    assert MSG_NONE in tokens.json()["message"]
    assert MSG_TOKENS not in tokens.json()["message"]
    groups = db_client.get(GROUPS, headers=owner)
    assert groups.json()["data"] == []
    assert MSG_NONE in groups.json()["message"]


def test_gwt_m23_1_enterprise_opened_zero_tokens(db_client, db_session):
    owner, tid = _confirm(db_client, db_session, "m23-1e", "plan_enterprise")
    tokens = db_client.get(TOKENS, headers=owner)
    assert tokens.status_code == 200, tokens.text
    assert tokens.json()["data"] == []
    assert MSG_TOKENS in tokens.json()["message"]
    assert MSG_NONE not in tokens.json()["message"]
    page = db_client.get(SKU, headers=owner)
    assert page.json()["data"]["status"] == "active"
    assert page.json()["data"]["can_issue"] is True
    assert MSG_NONE not in (page.json()["data"].get("empty_title") or "")


def test_gwt_m23_1_relay_opened_zero_tokens(db_client, db_session, monkeypatch):
    owner, tid = _confirm(db_client, db_session, "m23-1r", "relay", monkeypatch)
    tokens = db_client.get(TOKENS, headers=owner)
    assert tokens.json()["data"] == []
    assert MSG_TOKENS in tokens.json()["message"]
    assert MSG_NONE not in tokens.json()["message"]


def test_gwt_m12_4_plan_pro_still_unopened(db_client, db_session):
    owner, tid = _confirm(db_client, db_session, "m12-4r", "plan_pro")
    tokens = db_client.get(TOKENS, headers=owner)
    assert tokens.json()["data"] == []
    assert MSG_NONE in tokens.json()["message"]
    assert MSG_TOKENS not in tokens.json()["message"]
    page = db_client.get(SKU, headers=owner)
    assert page.json()["data"]["status"] == "none"
    assert page.json()["data"]["can_issue"] is False


def test_gwt_m23_3_issue_refused_when_unopened(db_client, db_session):
    owner, tid = make_tenant_owner_headers(db_session, slug="m23-3")
    resp = db_client.post(TOKENS, headers=owner, json={"group_id": 1, "name": "x"})
    assert resp.status_code == 422
    assert resp.json()["code"] == "RELAY_SKU_INACTIVE"
    assert MSG_NONE in resp.json()["message"]
    tokens = db_client.get(TOKENS, headers=owner)
    assert tokens.json()["data"] == []
