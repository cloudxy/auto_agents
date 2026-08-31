"""E0.1c MySQL 保真通道验证（工单 03）：MYSQL_FIDELITY=1 时 fixture 切真实 MySQL

Seam（工单预确认）：db_engine/db_session fixture 的模式切换行为。
默认（开关关闭）本模块整体跳过——SQLite 模式行为由 test_db_fixtures.py 覆盖。
"""
import pytest
from sqlalchemy import func, select, inspect as sa_inspect

from platform_core.models.user import User

from conftest import mysql_fidelity_enabled
from factories import build_user

pytestmark = pytest.mark.mysql_fidelity


@pytest.fixture(autouse=True)
def _require_fidelity_mode():
    """未开启保真模式时跳过（autouse 先于 db_engine 实例化，避免无谓建库）"""
    if not mysql_fidelity_enabled():
        pytest.skip("MYSQL_FIDELITY 未开启（默认 SQLite 模式）")


@pytest.mark.asyncio
async def test_engine_dialect_is_mysql(db_engine):
    """开关开启后引擎方言为 mysql（独立事实源：方言名字面量）"""
    assert db_engine.dialect.name == "mysql"


@pytest.mark.asyncio
async def test_write_read_roundtrip_on_mysql(db_engine, db_session):
    """建表 + 写读往返在真实 MySQL 上成立（通道冒烟）"""
    async with db_session() as s:
        s.add(build_user(username="fidelity-probe"))
        await s.commit()
        count = (
            await s.execute(select(func.count()).select_from(User))
        ).scalar_one()
    assert count == 1


def test_all_orm_tables_on_mysql(db_engine):
    """create_all 在 MySQL 上同样产出 14 表全清单（与 SQLite 同一独立事实源）"""
    import asyncio

    from test_db_fixtures import ALL_ORM_TABLES

    async def _tables():
        async with db_engine.connect() as conn:
            return await conn.run_sync(lambda c: set(sa_inspect(c).get_table_names()))

    assert asyncio.run(_tables()) == ALL_ORM_TABLES
