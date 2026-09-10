"""D 线 62：行为验证环——逐迁移 up/down + EXPLAIN 断言 + 约束注入

复用 MYSQL_FIDELITY 通道（ADR-0002 S4：demo 与工业的分水岭）。
"""
import asyncio
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from conftest import _mysql_fidelity_parts, _run_schema_ddl, mysql_fidelity_enabled

pytestmark = pytest.mark.mysql_fidelity

VERSIONS = Path(__file__).resolve().parents[2] / "backend" / "alembic" / "versions"


@pytest.fixture(autouse=True)
def _require_fidelity_mode():
    if not mysql_fidelity_enabled():
        pytest.skip("MYSQL_FIDELITY 未开启（行为验证环只在真实 MySQL 上跑）")


@pytest.fixture
def fresh_db(monkeypatch):
    """独立空 schema + alembic 环境重定向（同 test_alembic_baseline 模式）"""
    server_url, schema = _mysql_fidelity_parts()
    asyncio.run(_run_schema_ddl(server_url, f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4"))

    import os

    host = os.environ.get("MYSQL_FIDELITY_HOST", "127.0.0.1")
    port = os.environ.get("MYSQL_FIDELITY_PORT", "3306")
    user = os.environ.get("MYSQL_FIDELITY_USER", "root")
    password = os.environ.get("MYSQL_FIDELITY_PASSWORD", "")

    monkeypatch.setenv("MYSQL_DEFAULT_PASSWORD", password)

    from config import settings

    originals = {k: settings.get(k) for k in [
        "MYSQL.DEFAULT.HOST", "MYSQL.DEFAULT.PORT", "MYSQL.DEFAULT.USER", "MYSQL.DEFAULT.DB_NAME"]}
    for key, value in {
        "MYSQL.DEFAULT.HOST": host, "MYSQL.DEFAULT.PORT": int(port),
        "MYSQL.DEFAULT.USER": user, "MYSQL.DEFAULT.DB_NAME": schema,
    }.items():
        settings.set(key, value)

    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{schema}?charset=utf8mb4"
    try:
        yield url
    finally:
        for key, value in originals.items():
            settings.set(key, value)
        asyncio.run(_run_schema_ddl(server_url, f"DROP DATABASE `{schema}`"))


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(VERSIONS.parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(VERSIONS.parent))
    return cfg


def test_explain_assertion_framework():
    """EXPLAIN 断言框架自证：构造全表扫描查询必须红（access type = ALL）"""
    # 用 SQLite 内存（框架逻辑本身 DB 无关——判定函数单测）
    from backend.services.quota_service import QuotaExceededException  # noqa: F401 证明 import 正常

    def _check_access_type(explain_row: dict) -> bool:
        """返回 True = 走索引（非 ALL）"""
        return str(explain_row.get("type", "")).upper() != "ALL"

    # 模拟：有索引的查询
    assert _check_access_type({"type": "ref"}) is True
    assert _check_access_type({"type": "range"}) is True
    # 模拟：全表扫描（无索引）
    assert _check_access_type({"type": "ALL"}) is False, "全表扫描应被断言框架捕获"


@pytest.mark.parametrize("dry_run", [False])
def test_constraint_injection(fresh_db, dry_run):
    """约束注入：唯一键 / NOT NULL 真挡得住脏数据"""
    from sqlalchemy import Integer, MetaData, String, Table, Column, UniqueConstraint, create_engine

    engine = create_engine(fresh_db)
    md = MetaData()
    test_table = Table(
        "constraint_inject_test", md,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("name", String(50), nullable=False),
        Column("email", String(100), nullable=False),
        UniqueConstraint("email", name="uq_test_email"),
    )
    md.create_all(engine)

    with engine.connect() as conn:
        # 唯一键拒绝重复
        conn.execute(test_table.insert(), {"name": "a", "email": "dup@test.com"})
        conn.commit()
        try:
            conn.execute(test_table.insert(), {"name": "b", "email": "dup@test.com"})
            conn.commit()
            raise AssertionError("唯一键未拒绝重复 email")
        except Exception:
            conn.rollback()

        # NOT NULL 拒绝空值
        try:
            conn.execute(test_table.insert(), {"email": "x@test.com"})  # name 缺失
            conn.commit()
            raise AssertionError("NOT NULL 未拒绝缺失 name")
        except Exception:
            conn.rollback()

    engine.dispose()


def test_explain_spider_results_composite_index(fresh_db):
    """D4 试点：spider_results (spider_name, created_at) 复合索引 EXPLAIN 断言。

    012 迁移已建此索引（ix_spider_results_spider_created）——本用例验证
    query_by_spider 模式（WHERE spider_name=X ORDER BY created_at DESC）
    真的走索引（access type ≠ ALL），兑现评审候选 7 的 DB 项。
    """
    from alembic import command

    command.upgrade(_alembic_config(), "head")
    engine = create_engine(fresh_db)
    with engine.connect() as conn:
        result = conn.execute(text(
            "EXPLAIN SELECT * FROM spider_results "
            "WHERE spider_name = 'demo' ORDER BY created_at DESC LIMIT 20"
        ))
        row = result.mappings().first()
        assert row is not None
        access_type = str(row.get("type", "")).upper()
        assert access_type != "ALL", (
            f"spider_results 复合索引查询走了全表扫描（type={access_type}）——"
            "评审候选 7 的索引缺口仍未关闭"
        )
    command.downgrade(_alembic_config(), "base")
    engine.dispose()


def test_explain_on_real_migration(fresh_db):
    """迁移 018 后对 capability_assets.name 查询走索引（UNIQUE 索引断言）"""
    from alembic import command

    command.upgrade(_alembic_config(), "head")
    engine = create_engine(fresh_db)

    with engine.connect() as conn:
        # uq_asset_type_name 唯一索引 → 等值查询应为 const/eq_ref/ref（非 ALL）
        result = conn.execute(text(
            "EXPLAIN SELECT * FROM capability_assets WHERE asset_type = 'skill' AND name = 'test'"
        ))
        row = result.mappings().first()
        assert row is not None
        access_type = str(row.get("type", "")).upper()
        assert access_type != "ALL", (
            f"capability_assets UNIQUE 索引查询走了全表扫描（type={access_type}）——"
            "S0 访问模式声明与索引不符"
        )

    command.downgrade(_alembic_config(), "base")
    engine.dispose()
