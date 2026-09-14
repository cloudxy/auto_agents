"""T4：spider_results 租户+时间索引 EXPLAIN（MySQL 保真）。"""
import pytest
from sqlalchemy import text

from conftest import mysql_fidelity_enabled

pytestmark = pytest.mark.mysql_fidelity


@pytest.fixture(autouse=True)
def _require():
    if not mysql_fidelity_enabled():
        pytest.skip("MYSQL_FIDELITY 未开启")


@pytest.mark.asyncio
async def test_explain_spider_results_tenant_created(db_engine):
    async with db_engine.connect() as conn:
        plan = (await conn.execute(text(
            "EXPLAIN SELECT id FROM spider_results "
            "WHERE tenant_id = 1 AND created_at > NOW() - INTERVAL 7 DAY"
        ))).mappings().all()
    joined = " ".join(str(row) for row in plan).lower()
    assert "spider_results" in joined
