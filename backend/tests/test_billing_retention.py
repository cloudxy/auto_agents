"""C2 计费闭环 + S4 retention + C1 租户槽位。"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from backend.services.billing_service import BillingService
from backend.services.quota_service import DEFAULT_QUOTA
from backend.services.retention_service import RetentionService
from backend.services.spider_task_service import SpiderTaskService
from platform_core.exceptions import BusinessException
from platform_core.models.archive import ArchiveRecord
from platform_core.models.billing import Order, Plan, TenantSubscription
from platform_core.models.spider_result import SpiderResult
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant
from platform_core.queues import tenant_active_key
from platform_core.schemas.billing import OrderCreate


@pytest.mark.asyncio
async def test_confirm_paid_applies_plan_quota(db_session):
    async with db_session() as s:
        tenant = Tenant(slug="bill-co", name="Bill")
        plan = Plan(
            slug="pro-bill", name="专业档", price_cents=29900, period="month",
            is_public=1, quota_json='{"task_concurrency":20,"result_storage":500000}',
        )
        s.add_all([tenant, plan])
        await s.flush()
        order = Order(tenant_id=tenant.id, plan_id=plan.id, amount_cents=29900, status="pending")
        s.add(order)
        await s.commit()
        oid, tid = order.id, tenant.id
    async with db_session() as s:
        out = await BillingService(s).confirm_paid(oid)
        assert out.status == "paid"
        tenant = await s.get(Tenant, tid)
        assert tenant.quota["task_concurrency"] == 20
        sub = (await s.execute(
            select(TenantSubscription).where(TenantSubscription.tenant_id == tid)
        )).scalar_one()
        assert sub.status == "active"


@pytest.mark.asyncio
async def test_attach_free_plan_skips_when_missing(db_session):
    async with db_session() as s:
        tenant = Tenant(slug="free-miss", name="F")
        s.add(tenant)
        await s.commit()
        await BillingService(s).attach_free_plan(tenant.id)
        sub = (await s.execute(
            select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id)
        )).scalar_one_or_none()
        assert sub is None


@pytest.mark.asyncio
async def test_attach_free_plan_writes_subscription(db_session):
    async with db_session() as s:
        tenant = Tenant(slug="free-hit", name="F")
        s.add(Plan(slug="free", name="免费档", price_cents=0, period="month", is_public=1,
                   quota_json='{"task_concurrency":5}'))
        s.add(tenant)
        await s.commit()
        await BillingService(s).attach_free_plan(tenant.id)
        await s.commit()
        tenant = (await s.execute(select(Tenant).where(Tenant.slug == "free-hit"))).scalar_one()
        assert tenant.quota["task_concurrency"] == 5
        assert tenant.expires_at is None


def test_tenant_admin_cannot_confirm_order(admin_client):
    resp = admin_client.post("/api/v1/billing/orders/1/confirm")
    assert resp.status_code == 404
    assert resp.json()["code"] == "HTTP_404"


def test_tenant_admin_cannot_list_pending_orders(admin_client):
    resp = admin_client.get("/api/v1/billing/admin/orders")
    assert resp.status_code == 404
    assert resp.json()["code"] == "HTTP_404"


def test_create_order_rejects_unknown_channel():
    from pydantic import ValidationError

    from platform_core.schemas.billing import OrderCreate

    with pytest.raises(ValidationError):
        OrderCreate(plan_id=1, channel="paypal")


def test_list_plans_public(db_client):
    resp = db_client.get("/api/v1/billing/plans")
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)


@pytest.mark.asyncio
async def test_create_order_service(db_session):
    async with db_session() as s:
        tenant = Tenant(slug="ord-co", name="O")
        plan = Plan(slug="pro-ord", name="专业档", price_cents=29900, period="month", is_public=1)
        s.add_all([tenant, plan])
        await s.commit()
        from platform_core.exceptions import BusinessException
        with pytest.raises(BusinessException) as ei:
            await BillingService(s).create_order(
                tenant.id, "owner", OrderCreate(plan_id=plan.id, channel="offline"),
            )
        assert ei.value.code == "ORDER_STORY_CLOSED"


@pytest.mark.asyncio
async def test_list_pending_orders_excludes_paid(db_session):
    async with db_session() as s:
        tenant = Tenant(slug="pend-co", name="P")
        plan = Plan(slug="pro-pend", name="专业档", price_cents=100, period="month", is_public=1)
        s.add_all([tenant, plan])
        await s.flush()
        s.add(Order(tenant_id=tenant.id, plan_id=plan.id, amount_cents=100, status="pending", channel="wechat"))
        s.add(Order(tenant_id=tenant.id, plan_id=plan.id, amount_cents=100, status="paid", channel="offline"))
        await s.commit()
        pending = await BillingService(s).list_pending_orders()
        assert len(pending) == 1
        assert pending[0].channel == "wechat"


@pytest.mark.asyncio
async def test_retention_archives_old_results(db_engine, db_session):
    async with db_session() as s:
        tenant = Tenant(slug="ret-co", name="R", quota={"result_retention_days": 10})
        s.add(tenant)
        await s.flush()
        task = SpiderTask(spider_name="example", tenant_id=tenant.id, status="completed", params="{}")
        s.add(task)
        await s.flush()
        old = datetime.now(timezone.utc) - timedelta(days=40)
        s.add(SpiderResult(
            task_id=task.id, spider_name="example", url="https://old.example",
            title="old", tenant_id=tenant.id, created_at=old,
        ))
        s.add(SpiderResult(
            task_id=task.id, spider_name="example", url="https://new.example",
            title="new", tenant_id=tenant.id, created_at=datetime.now(timezone.utc),
        ))
        await s.commit()
        tid = tenant.id
    mgr = MagicMock()
    mgr.async_engines = {"DEFAULT": db_engine}
    with patch("backend.services.retention_service.get_manager", return_value=mgr):
        n = await RetentionService().run_once()
    assert n == 1
    async with db_session() as s:
        left = (await s.execute(select(SpiderResult).where(SpiderResult.tenant_id == tid))).scalars().all()
        assert len(left) == 1
        assert left[0].url == "https://new.example"
        archived = (await s.execute(select(ArchiveRecord))).scalars().all()
        assert len(archived) == 1
        assert archived[0].source_table == "spider_results"


@pytest.mark.asyncio
async def test_enqueue_uses_tenant_slot_key():
    svc = SpiderTaskService.__new__(SpiderTaskService)
    svc.session = MagicMock()
    svc.session.commit = AsyncMock()
    svc.session.refresh = AsyncMock()
    svc.repo = MagicMock()
    svc._check_enqueue_quota = AsyncMock()
    fake_redis = AsyncMock()
    fake_redis.scard.return_value = 2
    with (
        patch("backend.services.spider_task_service.get_async_redis", return_value=fake_redis),
        patch("backend.services.spider_task_service.settings") as fake_settings,
    ):
        fake_settings.get.return_value = 2
        with pytest.raises(BusinessException, match="进行中的任务"):
            await svc.enqueue("example", tenant_id=7)
    fake_redis.scard.assert_awaited()
    assert fake_redis.scard.await_args.args[0] == tenant_active_key(7, "example")


def test_default_quota_includes_retention_days():
    assert DEFAULT_QUOTA["result_retention_days"] == 90
