"""S1-6 大表 DDL 实测（工单 36）：spider_results 加列/索引/回填分批的耗时记录

结论落档 docs/plan/README.md §7.3 附录（排期依据，10.2-G）。本测试在保真通道
真实 MySQL 上执行并断言分批回填模板可用；耗时不设阈值（记录性质）。
"""
import time

import pytest
from sqlalchemy import create_engine, text

from conftest import mysql_fidelity_enabled

pytestmark = pytest.mark.mysql_fidelity


@pytest.fixture(autouse=True)
def _require_fidelity_mode():
    if not mysql_fidelity_enabled():
        pytest.skip("MYSQL_FIDELITY 未开启（DDL 实测只在真实 MySQL 上跑）")


def test_ddl_drill_records_timing(alembic_db_url):  # noqa: F811 复用 baseline 的 fixture
    """建压测表 → 批量插入 → 加列/加索引/分批回填，耗时打印（记录性质）"""
    engine = create_engine(alembic_db_url)
    drill = []
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE drill_results (id INT PRIMARY KEY AUTO_INCREMENT, payload TEXT)"))
        rows = 6000  # ~5000/批 × 2 批
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO drill_results (payload) VALUES (:p)"),
                [{"p": "x" * 200} for _ in range(rows)],
            )
        started = time.perf_counter()
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE drill_results ADD COLUMN tenant_id INT NULL"))
        drill.append(("add_column", round(time.perf_counter() - started, 3)))
        started = time.perf_counter()
        with engine.begin() as conn:
            conn.execute(text("CREATE INDEX ix_drill_tenant ON drill_results (tenant_id)"))
        drill.append(("add_index", round(time.perf_counter() - started, 3)))
        started = time.perf_counter()
        batch = 0
        with engine.begin() as conn:
            while True:
                result = conn.execute(text(
                    "UPDATE drill_results SET tenant_id = 1 WHERE tenant_id IS NULL LIMIT 5000"
                ))
                batch += 1
                if result.rowcount == 0:
                    break
        drill.append(("backfill_batches", round(time.perf_counter() - started, 3)))
        with engine.begin() as conn:
            remaining = conn.execute(text(
                "SELECT COUNT(*) FROM drill_results WHERE tenant_id IS NULL"
            )).scalar_one()
        assert remaining == 0  # 分批回填模板：清零验证
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS drill_results"))
        engine.dispose()
    print(f"\n[DDL 实测记录 rows={rows}] {drill}")
