"""T-14 N3 schema：orders widen / 凭据 / SKU 权益唯一键与非法开通兜底。

HTTP 结账 / 通道 SDK 验真不在本票。密钥不进 yml。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect as sa_inspect, select, update
from sqlalchemy.exc import IntegrityError

from backend.app.tenant_isolation import TENANT_EXEMPT_TABLES
from platform_core.models.billing import Order, Plan
from platform_core.models.payment_channel_credential import PaymentChannelCredential
from platform_core.models.relay import RelayGroup
from platform_core.models.relay_sku_entitlement import RelaySkuEntitlement
from platform_core.tenant_context import tenant_exempt_tables, tenant_scope

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_PLAIN = "not-a-merchant-secret"
_BLOB = "enc:v1:opaque-ciphertext-not-plaintext"


def test_046_revises_045_and_n1_file_has_no_n3_objects():
    n1 = (_VERSIONS / "045_n1_internal_fixture_tenants.py").read_text()
    n3 = (_VERSIONS / "046_n3_checkout_orders_credentials_sku.py").read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "045"' in n3
    assert 'revision: str = "046"' in n3
    for banned in ("payment_channel_credentials", "relay_sku_entitlements", "open_product_slot"):
        assert banned not in n1
    assert "drop_table(\"relay_groups\")" not in n3
    assert "drop_table('relay_groups')" not in n3


def test_credentials_exempt_entitlements_not():
    assert "payment_channel_credentials" in TENANT_EXEMPT_TABLES
    assert "payment_channel_credentials" in tenant_exempt_tables()
    assert "relay_sku_entitlements" not in TENANT_EXEMPT_TABLES
    assert "relay_sku_entitlements" not in tenant_exempt_tables()


@pytest.mark.asyncio
async def test_credentials_have_no_tenant_id_column(db_engine):
    async with db_engine.connect() as conn:
        cols = await conn.run_sync(
            lambda c: {x["name"] for x in sa_inspect(c).get_columns("payment_channel_credentials")}
        )
        tables = await conn.run_sync(lambda c: set(sa_inspect(c).get_table_names()))
    assert "tenant_id" not in cols
    assert "secrets_encrypted" in cols
    assert "relay_groups" in tables
    assert "relay_sku_entitlements" in tables


@pytest.mark.asyncio
async def test_channel_unique_and_ciphertext_not_plaintext(db_session):
    async with db_session() as s:
        s.add(PaymentChannelCredential(
            channel="alipay", merchant_no="2088mask", secrets_encrypted=_BLOB,
        ))
        await s.flush()
        s.add(PaymentChannelCredential(
            channel="alipay", merchant_no="other", secrets_encrypted=_BLOB + "2",
        ))
        with pytest.raises(IntegrityError):
            await s.flush()


@pytest.mark.asyncio
async def test_two_channels_ok_and_blob_ne_plaintext(db_session):
    async with db_session() as s:
        s.add_all([
            PaymentChannelCredential(channel="alipay", merchant_no="m1", secrets_encrypted=_BLOB),
            PaymentChannelCredential(channel="wechat", merchant_no="m2", secrets_encrypted=_BLOB),
        ])
        await s.commit()
        row = (await s.execute(
            select(PaymentChannelCredential).where(PaymentChannelCredential.channel == "alipay")
        )).scalar_one()
        assert row.secrets_encrypted == _BLOB
        assert row.secrets_encrypted != _PLAIN
        assert _PLAIN not in (row.secrets_encrypted or "")


@pytest.mark.asyncio
async def test_relay_sku_tenant_unique_and_not_null(db_session):
    async with db_session() as s:
        s.add(RelaySkuEntitlement(tenant_id=7, status="active"))
        await s.flush()
        s.add(RelaySkuEntitlement(tenant_id=7, status="none"))
        with pytest.raises(IntegrityError):
            await s.flush()


@pytest.mark.asyncio
async def test_relay_sku_null_tenant_rejected(db_session):
    async with db_session() as s:
        s.add(RelaySkuEntitlement(tenant_id=None, status="none"))
        with pytest.raises(IntegrityError):
            await s.flush()


@pytest.mark.asyncio
async def test_relay_groups_still_insertable(db_session):
    async with db_session() as s:
        s.add(RelayGroup(tenant_id=3, name="骨架组"))
        await s.commit()
        row = (await s.execute(select(RelayGroup))).scalar_one()
        assert row.name == "骨架组"


async def _seed_pro(s) -> Plan:
    row = (await s.execute(select(Plan).where(Plan.slug == "pro"))).scalar_one_or_none()
    if row is not None:
        return row
    plan = Plan(slug="pro", name="专业档", price_cents=29900, period="month", is_public=1)
    s.add(plan)
    await s.flush()
    return plan


def _order(**kw) -> Order:
    data = dict(tenant_id=11, amount_cents=29900, status="checkout_pending", channel="alipay")
    data.update(kw)
    return Order(**data)


@pytest.mark.asyncio
async def test_open_product_slot_unique_blocks_second_checkout(db_session):
    async with db_session() as s:
        await _seed_pro(s)
        s.add(_order(product_code="plan_pro", order_no="no-1"))
        await s.flush()
        s.add(_order(product_code="plan_pro", order_no="no-2", channel="wechat"))
        with pytest.raises(IntegrityError):
            await s.flush()


@pytest.mark.asyncio
async def test_fulfilled_releases_slot_second_checkout_ok(db_session):
    async with db_session() as s:
        await _seed_pro(s)
        first = _order(product_code="plan_pro", order_no="no-a", status="checkout_pending")
        s.add(first)
        await s.flush()
        await s.refresh(first)
        assert first.open_product_slot == "plan_pro"
        first.status = "fulfilled"
        await s.flush()
        await s.refresh(first)
        assert first.open_product_slot is None
        s.add(_order(product_code="plan_pro", order_no="no-b"))
        await s.flush()
        await s.refresh(first)
        second = (await s.execute(select(Order).where(Order.order_no == "no-b"))).scalar_one()
        assert second.open_product_slot == "plan_pro"


@pytest.mark.asyncio
async def test_unpaid_and_null_product_do_not_occupy_slot(db_session):
    async with db_session() as s:
        await _seed_pro(s)
        s.add(_order(product_code="plan_pro", status="unpaid", order_no="u1"))
        s.add(_order(product_code="plan_pro", status="checkout_pending", order_no="u2"))
        await s.flush()
        s.add(_order(product_code=None, status="pending", order_no=None, channel="offline"))
        s.add(_order(
            product_code=None, status="pending", order_no=None, channel="offline",
            idempotency_key="legacy-2",
        ))
        await s.flush()


@pytest.mark.asyncio
async def test_order_no_and_channel_trade_uniques(db_session):
    async with db_session() as s:
        await _seed_pro(s)
        s.add(_order(order_no="dup-no", product_code="relay", plan_id=None))
        await s.flush()
        s.add(_order(
            tenant_id=12, order_no="dup-no", product_code="relay", plan_id=None,
        ))
        with pytest.raises(IntegrityError):
            await s.flush()


@pytest.mark.asyncio
async def test_channel_trade_unique_same_channel(db_session):
    async with db_session() as s:
        await _seed_pro(s)
        s.add(_order(order_no="t1", channel_trade_no="trade-9", product_code="relay", plan_id=None))
        await s.flush()
        s.add(_order(
            tenant_id=12, order_no="t2", channel_trade_no="trade-9",
            product_code="relay", plan_id=None,
        ))
        with pytest.raises(IntegrityError):
            await s.flush()


@pytest.mark.asyncio
async def test_illegal_fulfill_cas_unpaid_rowcount_zero(db_session):
    """非法 unpaid→fulfilled：条件 UPDATE 影响 0 行（约束能兜底的开通精确一次原语）。"""
    async with db_session() as s:
        await _seed_pro(s)
        row = _order(product_code="relay", plan_id=None, status="unpaid", order_no="dead")
        s.add(row)
        await s.flush()
        oid = int(row.id)
        result = await s.execute(
            update(Order)
            .where(Order.id == oid, Order.status.in_(
                ("checkout_pending", "paid_pending_fulfillment"),
            ))
            .values(status="fulfilled")
            .execution_options(synchronize_session=False)
        )
        assert result.rowcount == 0
        stored = await s.get(Order, oid)
        assert stored is not None
        assert stored.status == "unpaid"


@pytest.mark.asyncio
async def test_cas_fulfill_from_checkout_pending_once(db_session):
    async with db_session() as s:
        await _seed_pro(s)
        row = _order(product_code="plan_pro", order_no="pay-1")
        s.add(row)
        await s.flush()
        oid = int(row.id)
        first = await s.execute(
            update(Order)
            .where(Order.id == oid, Order.status.in_(
                ("checkout_pending", "paid_pending_fulfillment"),
            ))
            .values(status="fulfilled")
            .execution_options(synchronize_session=False)
        )
        assert first.rowcount == 1
        second = await s.execute(
            update(Order)
            .where(Order.id == oid, Order.status.in_(
                ("checkout_pending", "paid_pending_fulfillment"),
            ))
            .values(status="fulfilled")
            .execution_options(synchronize_session=False)
        )
        assert second.rowcount == 0


@pytest.mark.asyncio
async def test_credentials_exempt_update_unfiltered(db_session):
    async with db_session() as s:
        s.add(PaymentChannelCredential(
            channel="alipay", merchant_no="m", secrets_encrypted=_BLOB,
        ))
        await s.commit()
    with tenant_scope(1):
        async with db_session() as s:
            result = await s.execute(
                update(PaymentChannelCredential).values(merchant_no="rotated")
                .execution_options(synchronize_session=False)
            )
            await s.commit()
            assert result.rowcount == 1
