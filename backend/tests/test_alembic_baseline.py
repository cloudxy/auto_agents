"""E0.2 Alembic 基线修复验证（工单 04）：空库 upgrade head 全链成功且与 create_all 对齐

Seam（工单预确认）：alembic command API（upgrade/downgrade）× 模型 create_all 的
交叉对拍——两条独立生产路径互为事实源，非同源回读。
"""
import asyncio
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect as sa_inspect

from conftest import _mysql_fidelity_parts, _run_schema_ddl, mysql_fidelity_enabled
from test_db_fixtures import ALL_ORM_TABLES

pytestmark = pytest.mark.mysql_fidelity

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _require_fidelity_mode():
    if not mysql_fidelity_enabled():
        pytest.skip("MYSQL_FIDELITY 未开启（迁移验证只在真实 MySQL 上跑）")


@pytest.fixture
def alembic_db_url(monkeypatch: pytest.MonkeyPatch) -> str:
    """独立 schema + settings 运行时重定向（Dynaconf 构造时快照环境变量，
    monkeypatch.setenv 无效；settings.set 为运行时写入口，config/__init__.py 同用法）。

    防误伤守卫：重定向后按 env.py 同式重算 URL，断言库名确为独立测试 schema——
    覆写失败时绝不让 alembic 跑向真实库。
    """
    server_url, schema = _mysql_fidelity_parts()
    asyncio.run(_run_schema_ddl(server_url, f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4"))

    host = os.environ.get("MYSQL_FIDELITY_HOST", "127.0.0.1")
    port = os.environ.get("MYSQL_FIDELITY_PORT", "3306")
    user = os.environ.get("MYSQL_FIDELITY_USER", "root")
    from urllib.parse import quote_plus

    password = quote_plus(os.environ.get("MYSQL_FIDELITY_PASSWORD", ""))

    monkeypatch.setenv("MYSQL_DEFAULT_PASSWORD", password)

    from config import settings

    overrides = {
        "MYSQL.DEFAULT.HOST": host,
        "MYSQL.DEFAULT.PORT": int(port),
        "MYSQL.DEFAULT.USER": user,
        "MYSQL.DEFAULT.DB_NAME": schema,
    }
    originals = {key: settings.get(key) for key in overrides}
    for key, value in overrides.items():
        settings.set(key, value)
    assert settings.MYSQL.DEFAULT.DB_NAME == schema, "settings 重定向未生效，中止以防跑向真实库"

    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{schema}?charset=utf8mb4"
    try:
        yield url
    finally:
        for key, value in originals.items():
            settings.set(key, value)
        asyncio.run(_run_schema_ddl(server_url, f"DROP DATABASE `{schema}`"))


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "backend" / "alembic"))
    return cfg


def _run_alembic(target: str) -> None:
    from alembic import command

    cfg = _alembic_config()
    command.upgrade(cfg, target) if target != "base" else command.downgrade(cfg, "base")


def _sync_inspect(url: str) -> dict[str, set[str]]:
    engine = create_engine(url)
    try:
        inspector = sa_inspect(engine)
        return {t: {c["name"] for c in inspector.get_columns(t)} for t in inspector.get_table_names()}
    finally:
        engine.dispose()


def test_fresh_upgrade_head_matches_create_all(db_engine, alembic_db_url: str):
    """空库 upgrade head：表集合 == create_all 表集合，且逐表列名集合一致"""
    _run_alembic("head")
    migrated = _sync_inspect(alembic_db_url)
    assert set(migrated) - {"alembic_version"} == ALL_ORM_TABLES

    async def _reference() -> dict[str, set[str]]:
        async with db_engine.connect() as conn:
            return await conn.run_sync(
                lambda c: {
                    t: {col["name"] for col in sa_inspect(c).get_columns(t)}
                    for t in sa_inspect(c).get_table_names()
                }
            )

    reference = asyncio.run(_reference())
    for table in ALL_ORM_TABLES:
        assert migrated[table] == reference[table], (
            f"表 {table} 列集不一致: 仅迁移有={migrated[table] - reference[table]} "
            f"仅模型有={reference[table] - migrated[table]}"
        )


def test_bootstrapped_db_upgrade_head_is_noop(alembic_db_url: str) -> None:
    """存量口径：create_all 预建 + stamp head 的库再 upgrade head 必须零报错零变更（幂等验收）"""
    import platform_core.models  # noqa: F401
    from alembic import command
    from platform_core.models.base import Base
    from sqlalchemy import create_engine

    engine = create_engine(alembic_db_url)
    Base.metadata.create_all(engine)
    engine.dispose()

    cfg = _alembic_config()
    command.stamp(cfg, "head")
    before = _sync_inspect(alembic_db_url)

    command.upgrade(cfg, "head")
    after = _sync_inspect(alembic_db_url)
    assert before == after, "幂等升级不应改变任何表结构"


def test_downgrade_base_leaves_nothing(alembic_db_url: str):
    """downgrade base 后无业务表残留（alembic_version 空壳除外）"""
    _run_alembic("head")
    _run_alembic("base")
    migrated = _sync_inspect(alembic_db_url)
    assert set(migrated) - {"alembic_version"} == set()
