"""账期生命周期（决策 D22 / D17，2026-09-29「按照建议做」）

- 到期：前 7 / 3 / 1 天各提醒一次（邮件给负责人）；到期后宽限 3 天；宽限过后降为免费档，
  数据保留、企业不停用（原巡检把企业整体置 expired、连续费页都进不去，且从未接进启动流程）
- 升档立即生效，旧档剩余天数按日价折算成新档天数；同档续费从原到期日顺延
- 高档有效期内不能自助买低档（到期后自动转免费档，再买）；企业档走「联系我们」，不能自助结账
- 巡检注册进应用启动流程
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from backend.tests.payment_notify_support import PRO_QUOTA, seed_plans
from conftest import make_tenant_owner_headers
from platform_core.models.billing import Plan, TenantSubscription
from platform_core.models.tenant import Tenant
from platform_core.timeutil import utcnow
from stubs import FakeRedis

CHECKOUT = "/api/v1/billing/checkout"


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def mailbox(monkeypatch):
    import backend.services.subscription_lifecycle as svc

    sent: list[tuple[str, str, str]] = []

    async def _send(to, subject, text, html=None):
        sent.append((to, subject, text))
        return True

    monkeypatch.setattr(svc, "send_mail", _send)
    monkeypatch.setattr(svc, "get_async_redis", lambda: redis)
    redis = FakeRedis()
    return sent


def _subscribe(db_session, tid: int, slug: str, end: datetime | None) -> None:
    async def _go():
        async with db_session() as s:
            plan = (await s.execute(select(Plan).where(Plan.slug == slug))).scalar_one()
            tenant = await s.get(Tenant, tid)
            tenant.quota = {**(json.loads(plan.quota_json) if plan.quota_json else {}),
                            "delivery_webhook_url": "https://hooks.example.com/x"}
            tenant.expires_at = end
            s.add(TenantSubscription(tenant_id=tid, plan_id=plan.id, status="active", current_period_end=end))
            await s.commit()

    _run(_go())


def _state(db_session, tid: int):
    async def _go():
        async with db_session() as s:
            sub = (await s.execute(select(TenantSubscription).where(TenantSubscription.tenant_id == tid))).scalar_one()
            plan = await s.get(Plan, sub.plan_id)
            tenant = await s.get(Tenant, tid)
            return plan.slug, sub.current_period_end, tenant.status, dict(tenant.quota or {}), tenant.expires_at

    return _run(_go())


def _patrol(db_session):
    from backend.services.subscription_lifecycle import SubscriptionLifecycleService

    async def _go():
        async with db_session() as s:
            return await SubscriptionLifecycleService().run_once(s)

    return _run(_go())


# ---------------- 升档折算 / 同档顺延 ----------------

def test_upgrade_credits_remaining_days(db_client, db_session):
    from backend.services.billing_fulfill import apply_plan_quota

    seed_plans(db_session)
    _owner, tid = make_tenant_owner_headers(db_session, slug="lc-up")
    now = utcnow()
    _subscribe(db_session, tid, "pro", now + timedelta(days=20))

    async def _go():
        async with db_session() as s:
            ent = (await s.execute(select(Plan).where(Plan.slug == "enterprise"))).scalar_one()
            await apply_plan_quota(s, tid, ent, now)
            await s.commit()

    _run(_go())
    slug, end, _status, _q, _exp = _state(db_session, tid)
    credit = timedelta(days=20) * 29900 / 99900  # 专业档剩 20 天的价值折成企业档天数
    assert slug == "enterprise"
    assert abs((end - (now + timedelta(days=30) + credit)).total_seconds()) < 5


# ---------------- 购买闸 ----------------

def test_cannot_self_buy_lower_plan_during_higher_period(db_client, db_session):
    seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="lc-down")
    _subscribe(db_session, tid, "enterprise", utcnow() + timedelta(days=10))
    resp = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"})
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "SUBSCRIPTION_DOWNGRADE_AT_PERIOD_END"


def test_enterprise_is_sales_led(db_client, db_session):
    seed_plans(db_session)
    owner, _tid = make_tenant_owner_headers(db_session, slug="lc-sales")
    resp = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_enterprise"})
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "PLAN_SALES_LED"
    plans = {p["slug"]: p for p in db_client.get("/api/v1/billing/plans").json()["data"]}
    assert plans["pro"]["sales_led"] is False
    if "enterprise" in plans:
        assert plans["enterprise"]["sales_led"] is True


# ---------------- 巡检：提醒 / 宽限 / 降档 ----------------

def test_reminder_sent_once_per_threshold(db_client, db_session, mailbox):
    seed_plans(db_session)
    _owner, tid = make_tenant_owner_headers(db_session, slug="lc-remind")
    _subscribe(db_session, tid, "pro", utcnow() + timedelta(days=2, hours=20))
    _patrol(db_session)
    _patrol(db_session)
    assert len(mailbox) == 1  # 只发最近的一档（3 天），不补发 7 天那封，也不重复
    to, subject, text = mailbox[0]
    assert to == "owner-lc-remind@x.com"
    assert "3 天" in subject and "续费" in text


def test_within_grace_keeps_paid_plan(db_client, db_session, mailbox):
    seed_plans(db_session)
    _owner, tid = make_tenant_owner_headers(db_session, slug="lc-grace")
    _subscribe(db_session, tid, "pro", utcnow() - timedelta(days=1))
    _patrol(db_session)
    slug, _end, status, quota, _exp = _state(db_session, tid)
    assert slug == "pro" and status == "active"
    assert quota["task_concurrency"] == PRO_QUOTA["task_concurrency"]


def test_after_grace_downgrades_to_free_and_keeps_company_active(db_client, db_session, mailbox):
    seed_plans(db_session)
    _owner, tid = make_tenant_owner_headers(db_session, slug="lc-expire")
    _subscribe(db_session, tid, "pro", utcnow() - timedelta(days=4))
    result = _patrol(db_session)
    slug, end, status, quota, expires_at = _state(db_session, tid)
    assert result["downgraded"] == 1
    assert slug == "free" and end is None and expires_at is None
    assert status == "active"  # 不再停用整家企业
    assert "task_concurrency" not in quota  # 套餐配额撤掉 → 按免费档默认
    assert quota["delivery_webhook_url"] == "https://hooks.example.com/x"  # 企业自己的设置保留
    assert any("已转为免费档" in subject for _to, subject, _t in mailbox)
    _patrol(db_session)  # 幂等：再跑不重复降档、不重复发信
    assert sum("已转为免费档" in subject for _to, subject, _t in mailbox) == 1


def test_expired_company_can_still_log_in_and_renew(db_client, db_session, mailbox):
    """降档后负责人照常登录、能进结账续费（原先整家企业被锁，连续费页都进不去）"""
    seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="lc-renew")
    _subscribe(db_session, tid, "pro", utcnow() - timedelta(days=5))
    _patrol(db_session)
    resp = db_client.post(CHECKOUT, headers=owner, json={"product": "plan_pro"})
    assert resp.status_code == 201, resp.text


def test_patrol_registered_in_app_lifespan():
    import inspect

    import backend.app as app_module

    source = inspect.getsource(app_module)
    assert "SubscriptionLifecycleService" in source


def test_subscription_api_reports_plan_and_grace(db_client, db_session):
    """用量页要显示「当前套餐 / 到期日 / 宽限到哪天」"""
    seed_plans(db_session)
    owner, tid = make_tenant_owner_headers(db_session, slug="lc-api")
    end = utcnow() - timedelta(days=1)
    _subscribe(db_session, tid, "pro", end)
    data = db_client.get("/api/v1/billing/subscription", headers=owner).json()["data"]
    assert data["plan_slug"] == "pro" and data["plan_name"] == "专业档"
    assert data["in_grace"] is True
    grace = datetime.fromisoformat(data["grace_until"].replace("Z", "+00:00")).replace(tzinfo=None)
    assert abs((grace - (end + timedelta(days=3))).total_seconds()) < 2
