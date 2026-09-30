"""历史时间换算脚本（审计 BUG-43）：分类、ON UPDATE 保护、防重复换算

分类为纯函数（常规跑）；换算本身在真实 MySQL 隔离库上验证（MYSQL_FIDELITY=1）。
"""
import importlib.util
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from conftest import mysql_fidelity_enabled
from test_alembic_baseline import _alembic_config, alembic_db_url  # noqa: F401 (fixture)

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "db" / "utc_backfill.py"


def _load():
    spec = importlib.util.spec_from_file_location("utc_backfill", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_classify_columns():
    m = _load()
    assert m.classify("orders", "created_at", "datetime") == "legacy"      # 库默认值
    assert m.classify("orders", "paid_at", "datetime") == "utc"            # Python UTC
    assert m.classify("capability_assets", "deleted_at", "datetime") == "utc"
    assert m.classify("users", "deleted_at", "datetime") == "legacy"       # repository func.now()
    assert m.classify("spider_tasks", "started_at", "datetime") == "legacy"
    assert m.classify("x", "created_at", "timestamp") == "tz"
    assert m.classify("x", "mystery_at", "datetime") == "unknown"


def test_on_update_column_is_pinned_when_not_shifted():
    m = _load()
    cols = [
        {"table": "t", "column": "created_at", "kind": "legacy", "n": 1, "on_update": False},
        {"table": "t", "column": "seen_at", "kind": "utc", "n": 1, "on_update": True},
    ]
    assert m.build_statements(cols, 480) == [
        "UPDATE `t` SET `created_at` = `created_at` - INTERVAL 480 MINUTE, `seen_at` = `seen_at`"
    ]


def test_cutoff_skips_rows_written_after_switch():
    """新代码上线后写入的行已是 UTC：--written-before 之后的读数原样保留"""
    m = _load()
    cols = [{"table": "t", "column": "updated_at", "kind": "legacy", "n": 2, "on_update": False}]
    assert m.build_statements(cols, 480, cutoff=datetime(2026, 9, 29, 1, 0)) == [
        "UPDATE `t` SET `updated_at` = IF(`updated_at` < '2026-09-29 01:00:00', "
        "`updated_at` - INTERVAL 480 MINUTE, `updated_at`)"
    ]


@pytest.fixture
def _fidelity_only():
    """排在 alembic_db_url 之前：未开真库模式时先跳过（否则夹具先去建库而报错）"""
    if not mysql_fidelity_enabled():
        pytest.skip("MYSQL_FIDELITY 未开启")


@pytest.mark.mysql_fidelity
def test_apply_shifts_legacy_only_and_refuses_second_run(_fidelity_only, alembic_db_url):  # noqa: F811
    from alembic import command

    m = _load()
    command.upgrade(_alembic_config(), "head")
    engine = create_engine(alembic_db_url)
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO product_events (event_name, occurred_at, created_at, updated_at) "
                "VALUES ('x', '2026-09-14 01:00:00', '2026-09-14 09:00:00', '2026-09-14 09:00:00')"))
            conn.execute(text(
                "INSERT INTO system_configs (config_key, config_value, updated_at) "
                "VALUES ('site.name', 'A', '2026-09-03 13:56:12')"))
            # 切换后（新代码、会话 UTC）写入的行
            conn.execute(text(
                "INSERT INTO product_events (event_name, occurred_at, created_at, updated_at) "
                "VALUES ('y', '2026-09-29 01:27:47', '2026-09-29 01:27:47', '2026-09-29 01:27:47')"))
        with engine.connect() as conn:
            trans = conn.begin()
            cols = m.load_columns(conn)
            assert m.apply(conn, cols, 480, cutoff=datetime(2026, 9, 29, 1, 0)) == 0
            trans.commit()
        with engine.connect() as conn:
            ev = conn.execute(text("SELECT occurred_at, created_at FROM product_events WHERE event_name='x'")).one()
            post = conn.execute(text("SELECT created_at FROM product_events WHERE event_name='y'")).scalar_one()
            assert post == datetime(2026, 9, 29, 1, 27, 47)   # 切换后写入：不动
            cfg = conn.execute(text(
                "SELECT updated_at FROM system_configs WHERE config_key='site.name'")).scalar_one()
            assert tuple(ev) == (datetime(2026, 9, 14, 1, 0), datetime(2026, 9, 14, 1, 0))
            # ON UPDATE CURRENT_TIMESTAMP 列被显式赋值：换算而不是被刷成 NOW()
            assert cfg == datetime(2026, 9, 3, 5, 56, 12)
            assert m.read_marker(conn)
        with engine.connect() as conn:
            trans = conn.begin()
            assert m.apply(conn, m.load_columns(conn), 480) == 2   # 标记在：拒绝减第二次
            trans.rollback()
    finally:
        engine.dispose()
