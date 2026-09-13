"""T-17/T-22 测试夹具：配通道、建待支付、签通知。禁止把密钥写进断言全文。"""
from __future__ import annotations

import asyncio
import json
import uuid

from cryptography.fernet import Fernet
from sqlalchemy import select

from backend.services.channel_notify_auth import notify_mac
from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.billing import Order, Plan, TenantSubscription
from platform_core.models.relay_sku_entitlement import RelaySkuEntitlement
from platform_core.models.tenant import Tenant

CHECKOUT = "/api/v1/billing/checkout"
CRED = "/api/v1/admin/payment-credentials"
EVENTS = "/api/v1/product-events"
NOTIFY = "/api/v1/billing/notify"
SKU = "/api/v1/relay/sku"
TOKENS = "/api/v1/relay/tokens"
SUB = "/api/v1/billing/subscription"
GHOST = "/api/v1/admin/tenants"
BANNED = "当前可买"
PRO_QUOTA = {
    "task_concurrency": 20, "result_storage": 500000, "llm_tokens_month": 5000000,
}
ENT_QUOTA = {
    "task_concurrency": 50, "result_storage": 2000000, "llm_tokens_month": 20000000,
}


def install_fernet(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENCRYPTION_KEY", Fernet.generate_key().decode())


def seed_plans(db_session) -> None:
    async def _go():
        async with db_session() as s:
            if (await s.execute(select(Plan).where(Plan.slug == "pro"))).scalar_one_or_none():
                return
            s.add_all([
                Plan(slug="free", name="免费档", price_cents=0, period="month", is_public=1),
                Plan(
                    slug="pro", name="专业档", price_cents=29900, period="month",
                    quota_json=json.dumps(PRO_QUOTA), is_public=1,
                ),
                Plan(
                    slug="enterprise", name="企业档", price_cents=99900, period="month",
                    quota_json=json.dumps(ENT_QUOTA), is_public=0,
                ),
            ])
            await s.commit()

    asyncio.run(_go())


def put_channel(db_client, db_session, channel: str, secret: str | None = None):
    secret = secret or ("sk-t17-" + uuid.uuid4().hex)
    merchant = f"mch-{channel}-{uuid.uuid4().hex[:8]}"
    pa = make_platform_admin_headers(db_session)
    resp = db_client.put(CRED, headers=pa, json={
        "channel": channel, "merchant_no": merchant, "secrets": secret,
    })
    assert resp.status_code == 200, resp.text
    return pa, secret, merchant


def signed_body(
    secret: str, channel: str, order_no: str, merchant_no: str, amount_cents: int,
    trade_status: str = "success", **extra,
) -> dict:
    body = {
        "order_no": order_no, "merchant_no": merchant_no,
        "amount_cents": amount_cents, "trade_status": trade_status, **extra,
    }
    body["sign"] = notify_mac(
        secret, channel=channel, order_no=order_no, merchant_no=merchant_no,
        amount_cents=amount_cents, trade_status=trade_status,
    )
    return body


def post_notify(db_client, channel: str, body: dict):
    return db_client.post(f"{NOTIFY}/{channel}", json=body)


def checkout(
    db_client, db_session, *, slug: str, product: str = "plan_pro",
    channel: str = "alipay",
):
    seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug=slug)
    pa, secret, merchant = put_channel(db_client, db_session, channel)
    resp = db_client.post(
        CHECKOUT, headers=owner, json={"product": product, "channel": channel},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    return {
        "owner": owner, "tid": tid, "pa": pa, "secret": secret, "merchant": merchant,
        "order": data, "channel": channel, "product": product,
    }


def patch_relay_price(monkeypatch, cents: int = 19900):
    import backend.services.billing_service as billing_mod

    orig = billing_mod.settings.get

    def _get(key, default=None):
        if key == "BILLING.RELAY_PRICE_CENTS":
            return cents
        return orig(key, default)

    monkeypatch.setattr(billing_mod.settings, "get", _get)


def order_row(db_session, tid: int) -> dict | None:
    async def _go():
        async with db_session() as s:
            row = (await s.execute(
                select(Order).where(Order.tenant_id == tid).order_by(Order.id.desc())
            )).scalars().first()
            if row is None:
                return None
            return {
                "id": int(row.id), "status": row.status, "fail": row.fail_reason,
                "product": row.product_code, "channel": row.channel,
                "late": row.late_notify_at, "verified": row.verified_at,
                "fulfilled": row.fulfilled_at, "amount": int(row.amount_cents),
                "order_no": row.order_no, "plan_id": row.plan_id,
            }

    return asyncio.run(_go())


def tenant_quota(db_session, tid: int):
    async def _go():
        async with db_session() as s:
            t = (await s.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
            return t.quota

    return asyncio.run(_go())


def sub_plan_slug(db_session, tid: int) -> str | None:
    async def _go():
        async with db_session() as s:
            sub = (await s.execute(
                select(TenantSubscription).where(TenantSubscription.tenant_id == tid)
            )).scalar_one_or_none()
            if sub is None:
                return None
            plan = await s.get(Plan, sub.plan_id)
            return None if plan is None else str(plan.slug)

    return asyncio.run(_go())


def sku_status(db_session, tid: int) -> str:
    async def _go():
        async with db_session() as s:
            row = (await s.execute(
                select(RelaySkuEntitlement).where(RelaySkuEntitlement.tenant_id == tid)
            )).scalar_one_or_none()
            return "none" if row is None else str(row.status)

    return asyncio.run(_go())


def sku_count(db_session, tid: int) -> int:
    async def _go():
        async with db_session() as s:
            rows = (await s.execute(
                select(RelaySkuEntitlement).where(RelaySkuEntitlement.tenant_id == tid)
            )).scalars().all()
            return len(rows)

    return asyncio.run(_go())


def event_items(db_client, pa, name: str, tenant_id: int | None = None) -> list:
    params = {"event_name": name}
    if tenant_id is not None:
        params["tenant_id"] = tenant_id
    resp = db_client.get(EVENTS, headers=pa, params=params)
    assert resp.status_code == 200, resp.text
    return list(resp.json()["data"]["items"])
