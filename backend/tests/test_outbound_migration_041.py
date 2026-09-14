"""T-04 迁移 041 可逆性：outbound_keys 新表 + relay_tokens expand 两列。

db-spec §14：up → down → up 三连在隔离库（真实 MySQL，MYSQL_FIDELITY=1）
跑并退出码 0；down 只在隔离库验证（生产禁止 downgrade past 037）。
默认 SQLite 会话跑不了迁移链（方言差异），本文件全部 mysql_fidelity 标记。
"""
import pytest
from sqlalchemy import create_engine, inspect as sa_inspect

from conftest import mysql_fidelity_enabled
from test_alembic_baseline import _alembic_config, alembic_db_url  # noqa: F401 (fixture)

pytestmark = pytest.mark.mysql_fidelity


@pytest.fixture(autouse=True)
def _require_fidelity_mode():
    if not mysql_fidelity_enabled():
        pytest.skip("MYSQL_FIDELITY 未开启（迁移验证只在真实 MySQL 上跑）")


def _columns(url: str, table: str) -> set[str]:
    engine = create_engine(url)
    try:
        inspector = sa_inspect(engine)
        if table not in inspector.get_table_names():
            return set()
        return {c["name"] for c in inspector.get_columns(table)}
    finally:
        engine.dispose()


def _index_names(url: str, table: str) -> set[str]:
    engine = create_engine(url)
    try:
        return {ix["name"] for ix in sa_inspect(engine).get_indexes(table)}
    finally:
        engine.dispose()


def test_migration_041_up_down_up_reversible(alembic_db_url):  # noqa: F811 (fixture 注入)
    """040 → 041 → 040 → 041：结构出现/消失/再出现，全程零异常退出。"""
    from alembic import command

    cfg = _alembic_config()

    # up（全链到 041）
    command.upgrade(cfg, "head")
    outbound_cols = _columns(alembic_db_url, "outbound_keys")
    assert outbound_cols == {
        "id", "tenant_id", "name", "key_prefix", "key_hash",
        "issued_by_user_id", "revoked_at", "created_at", "updated_at",
    }
    relay_cols = _columns(alembic_db_url, "relay_tokens")
    assert {"gateway_key_id", "spend_synced_at"} <= relay_cols  # T-08 备列
    assert "idx_outbound_keys_tenant_created" in _index_names(alembic_db_url, "outbound_keys")

    # down（单步回 040，只在隔离库）
    command.downgrade(cfg, "040")
    assert _columns(alembic_db_url, "outbound_keys") == set()  # 表已撤
    relay_cols_after = _columns(alembic_db_url, "relay_tokens")
    assert "gateway_key_id" not in relay_cols_after
    assert "spend_synced_at" not in relay_cols_after

    # up（再次到 041，可重放）
    command.upgrade(cfg, "head")
    assert "key_hash" in _columns(alembic_db_url, "outbound_keys")
    assert "gateway_key_id" in _columns(alembic_db_url, "relay_tokens")
