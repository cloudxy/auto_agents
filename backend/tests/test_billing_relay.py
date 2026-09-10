"""Wave 2/3 骨架：线下挂账 + 租户渠道组。在线支付未开通。"""
import asyncio

from sqlalchemy import select

from platform_core.models.billing import Plan, TenantSubscription
from platform_core.models.tenant import Tenant


def _seed_plans(db_session) -> None:
    async def _go():
        async with db_session() as s:
            if (await s.execute(select(Plan).where(Plan.slug == "free"))).scalar_one_or_none():
                return
            s.add_all([
                Plan(slug="free", name="免费档", price_cents=0, period="month",
                     quota_json='{"task_concurrency":5,"result_storage":10000,"llm_tokens_month":200000}',
                     is_public=1),
                Plan(slug="pro", name="专业档", price_cents=29900, period="month",
                     quota_json='{"task_concurrency":20,"result_storage":500000,"llm_tokens_month":5000000}',
                     is_public=1),
            ])
            await s.commit()
    asyncio.run(_go())


def test_list_plans_and_offline_order(
    db_client, db_session, db_engine,
):
    from conftest import make_platform_admin_headers, make_tenant_owner_headers

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="bill-co")
    plans = db_client.get("/api/v1/billing/plans")
    assert plans.status_code == 200
    slugs = {p["slug"] for p in plans.json()["data"]}
    assert "free" in slugs and "pro" in slugs
    pro_id = next(p["id"] for p in plans.json()["data"] if p["slug"] == "pro")

    blocked = db_client.post(
        "/api/v1/billing/orders",
        headers=owner,
        json={"plan_id": pro_id, "channel": "alipay"},
    )
    assert blocked.status_code == 400
    assert blocked.json()["code"] == "PAYMENT_NOT_CONFIGURED"

    created = db_client.post(
        "/api/v1/billing/orders",
        headers=owner,
        json={"plan_id": pro_id, "channel": "offline"},
    )
    assert created.status_code == 201, created.text
    order_id = created.json()["data"]["id"]
    assert created.json()["data"]["status"] == "pending"

    pa = make_platform_admin_headers(db_session)
    pending = db_client.get("/api/v1/billing/admin/orders", headers=pa)
    assert pending.status_code == 200
    assert any(o["id"] == order_id for o in pending.json()["data"])

    paid = db_client.post(f"/api/v1/billing/orders/{order_id}/confirm", headers=pa)
    assert paid.status_code == 200, paid.text
    assert paid.json()["data"]["status"] == "paid"

    async def _quota():
        async with db_session() as s:
            t = (await s.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
            sub = (await s.execute(
                select(TenantSubscription).where(TenantSubscription.tenant_id == tid)
            )).scalar_one()
            return t.quota, sub.plan_id
    quota, plan_id = asyncio.run(_quota())
    assert quota["task_concurrency"] == 20
    assert plan_id == pro_id


def test_viewer_cannot_create_order_or_token(db_client, db_session, db_engine):
    from conftest import make_tenant_owner_headers
    from backend.services.auth_service import AuthService
    from platform_core.models.user import User

    _seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="view-co")

    async def _viewer():
        async with db_session() as s:
            u = User(
                username="v1", email="v1@x.co", password_hash="x",
                role="viewer", tenant_id=tid, tenant_role="viewer", is_active=True,
            )
            s.add(u)
            await s.commit()
            await s.refresh(u)
            token = await AuthService(s).create_token({
                "id": u.id, "username": u.username, "is_admin": False, "role": "viewer",
                "tenant_id": tid, "tenant_role": "viewer", "is_platform_admin": False,
            })
            return token.access_token
    headers = {"Authorization": f"Bearer {asyncio.run(_viewer())}"}
    pro = next(p for p in db_client.get("/api/v1/billing/plans").json()["data"] if p["slug"] == "pro")
    resp = db_client.post("/api/v1/billing/orders", headers=headers, json={"plan_id": pro["id"]})
    assert resp.status_code == 403
    groups = db_client.get("/api/v1/relay/groups", headers=headers)
    assert groups.status_code == 200
    issue = db_client.post(
        "/api/v1/relay/tokens", headers=headers,
        json={"group_id": groups.json()["data"][0]["id"], "name": "nope"},
    )
    assert issue.status_code == 403


def test_relay_group_token_issue_and_revoke(db_client, db_session, db_engine):
    from conftest import make_tenant_owner_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="relay-co")
    listed = db_client.get("/api/v1/relay/groups", headers=owner)
    assert listed.status_code == 200, listed.text
    groups = listed.json()["data"]
    assert len(groups) == 1
    assert groups[0]["name"] == "default"
    gid = groups[0]["id"]

    created = db_client.post(
        "/api/v1/relay/groups", headers=owner,
        json={"name": "vip", "rpm_limit": 60, "tpm_limit": 10000, "models": ["gpt-4o"]},
    )
    assert created.status_code == 201, created.text
    vip = created.json()["data"]["id"]

    issued = db_client.post(
        "/api/v1/relay/tokens", headers=owner,
        json={"group_id": vip, "name": "ci", "quota_tokens": 1000},
    )
    assert issued.status_code == 201, issued.text
    body = issued.json()["data"]
    assert body["plaintext_key"].startswith("sk-")
    assert body["key_prefix"].startswith("sk-")
    token_id = body["id"]

    listed_tokens = db_client.get("/api/v1/relay/tokens", headers=owner)
    assert listed_tokens.status_code == 200
    row = listed_tokens.json()["data"][0]
    assert row["plaintext_key"] is None
    assert row["id"] == token_id

    other, _ = make_tenant_owner_headers(db_session, slug="other-co")
    stolen = db_client.patch(
        f"/api/v1/relay/groups/{gid}", headers=other, json={"status": "disabled"},
    )
    assert stolen.status_code == 404

    revoked = db_client.delete(f"/api/v1/relay/tokens/{token_id}", headers=owner)
    assert revoked.status_code == 200
    assert revoked.json()["data"]["status"] == "revoked"


def test_tenant_still_cannot_write_platform_channels(db_client, db_session, db_engine):
    from conftest import make_tenant_owner_headers

    owner, _ = make_tenant_owner_headers(db_session, slug="no-na")
    resp = db_client.get("/api/v1/newapi/channels", headers=owner)
    assert resp.status_code in (403, 404)
