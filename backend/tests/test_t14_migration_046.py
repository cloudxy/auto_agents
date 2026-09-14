"""T-14 迁移 046 可逆性：orders expand + 凭据 + SKU 权益。

up → down → up 在隔离库（真实 MySQL，MYSQL_FIDELITY=1）。
STORED GENERATED + UNIQUE 与 SQLite 不完全同构，本文件钉 MySQL 8。
禁止 DROP relay_groups。生产禁止 downgrade past 037。
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect as sa_inspect, text
from sqlalchemy.exc import IntegrityError

from conftest import mysql_fidelity_enabled
from test_alembic_baseline import _alembic_config, alembic_db_url  # noqa: F401

pytestmark = pytest.mark.mysql_fidelity

_ORDER_NEW = {
    "product_code", "order_no", "channel_trade_no", "merchant_id_snapshot",
    "fail_reason", "late_notify_at", "verified_at", "fulfilled_at", "unpaid_at",
    "open_product_slot", "updated_at",
}
_CRED_COLS = {
    "id", "channel", "merchant_no", "secrets_encrypted", "key_version",
    "rotated_at", "created_by", "updated_by", "created_at", "updated_at",
}
_SKU_COLS = {
    "id", "tenant_id", "status", "period_end", "activated_at", "created_at", "updated_at",
}


@pytest.fixture(autouse=True)
def _require_fidelity_mode():
    if not mysql_fidelity_enabled():
        pytest.skip("MYSQL_FIDELITY 未开启（迁移验证只在真实 MySQL 上跑）")


def _columns(url: str, table: str) -> set[str]:
    engine = create_engine(url)
    try:
        return {c["name"] for c in sa_inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(sa_inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _uniques(url: str, table: str) -> dict[str, list[str]]:
    engine = create_engine(url)
    try:
        insp = sa_inspect(engine)
        out: dict[str, list[str]] = {}
        for ix in insp.get_indexes(table):
            if ix.get("unique"):
                out[str(ix["name"])] = list(ix["column_names"])
        for uq in insp.get_unique_constraints(table):
            out[str(uq["name"])] = list(uq["column_names"])
        return out
    finally:
        engine.dispose()


def _show_create(url: str, table: str) -> str:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            row = conn.execute(text(f"SHOW CREATE TABLE `{table}`")).one()
            return str(row[1])
    finally:
        engine.dispose()


def _status_len(url: str) -> int:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return int(conn.execute(text(
                "SELECT CHARACTER_MAXIMUM_LENGTH FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'orders' "
                "AND COLUMN_NAME = 'status'"
            )).scalar_one())
    finally:
        engine.dispose()


def test_migration_046_up_down_up_uniques_and_no_drop_groups(alembic_db_url):  # noqa: F811
    from alembic import command

    cfg = _alembic_config()
    command.upgrade(cfg, "045")
    assert "payment_channel_credentials" not in _tables(alembic_db_url)
    assert "open_product_slot" not in _columns(alembic_db_url, "orders")
    assert "relay_groups" in _tables(alembic_db_url)

    command.upgrade(cfg, "046")
    _assert_046_shape(alembic_db_url)
    _assert_046_uniques(alembic_db_url)

    command.downgrade(cfg, "045")
    assert "payment_channel_credentials" not in _tables(alembic_db_url)
    assert "relay_sku_entitlements" not in _tables(alembic_db_url)
    assert "open_product_slot" not in _columns(alembic_db_url, "orders")
    assert "updated_at" not in _columns(alembic_db_url, "plans")
    assert "relay_groups" in _tables(alembic_db_url)
    assert _status_len(alembic_db_url) == 16

    command.upgrade(cfg, "046")
    _assert_046_shape(alembic_db_url)
    _assert_046_uniques(alembic_db_url)


def _assert_046_shape(url: str) -> None:
    assert _ORDER_NEW <= _columns(url, "orders")
    assert _columns(url, "payment_channel_credentials") == _CRED_COLS
    assert "tenant_id" not in _columns(url, "payment_channel_credentials")
    assert _columns(url, "relay_sku_entitlements") == _SKU_COLS
    assert "relay_groups" in _tables(url)
    assert _status_len(url) == 32
    ddl = _show_create(url, "orders")
    assert "GENERATED ALWAYS AS" in ddl
    assert "STORED" in ddl
    assert "uk_orders_tenant_open_product" in ddl
    assert "ix_orders_tenant_id" in ddl
    cred = _show_create(url, "payment_channel_credentials")
    assert "uk_payment_channel_credentials_channel" in cred
    assert "tenant_id" not in cred


def _assert_046_uniques(url: str) -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO orders (tenant_id, plan_id, amount_cents, status, channel, "
                "product_code, order_no) VALUES (1, NULL, 100, 'checkout_pending', "
                "'alipay', 'relay', 'ord-1')"
            ))
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO orders (tenant_id, plan_id, amount_cents, status, channel, "
                    "product_code, order_no) VALUES (1, NULL, 100, 'checkout_pending', "
                    "'wechat', 'relay', 'ord-2')"
                ))
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE orders SET status = 'fulfilled' WHERE order_no = 'ord-1'"
            ))
            conn.execute(text(
                "INSERT INTO orders (tenant_id, plan_id, amount_cents, status, channel, "
                "product_code, order_no) VALUES (1, NULL, 100, 'checkout_pending', "
                "'alipay', 'relay', 'ord-3')"
            ))
        _assert_credential_and_sku_uniques(engine, url)
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM orders"))
            conn.execute(text("DELETE FROM payment_channel_credentials"))
            conn.execute(text("DELETE FROM relay_sku_entitlements"))
    finally:
        engine.dispose()


def _assert_credential_and_sku_uniques(engine, url: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO payment_channel_credentials "
            "(channel, merchant_no, secrets_encrypted) "
            "VALUES ('alipay', '2088x', 'enc:v1:blob')"
        ))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO payment_channel_credentials "
                "(channel, merchant_no, secrets_encrypted) "
                "VALUES ('alipay', '2088y', 'enc:v1:other')"
            ))
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO relay_sku_entitlements (tenant_id, status) VALUES (9, 'active')"
        ))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO relay_sku_entitlements (tenant_id, status) VALUES (9, 'none')"
            ))
    uq_orders = _uniques(url, "orders")
    assert uq_orders.get("uk_orders_tenant_open_product") == ["tenant_id", "open_product_slot"]
    assert uq_orders.get("uk_orders_order_no") == ["order_no"]
    assert uq_orders.get("uk_orders_channel_trade") == ["channel", "channel_trade_no"]
