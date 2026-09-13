"""T-35 迁移 043 可逆性：asset_import_batches / asset_import_items 两表。

db-spec §16.5：up → down → up 三连在隔离库（真实 MySQL，MYSQL_FIDELITY=1）
跑并退出码 0；items.batch_id CASCADE（明细=批的组合子行）、items.asset_id →
capability_assets RESTRICT（provenance 回放链保链）。默认 SQLite 会话跑不了
迁移链（方言差异），全部 mysql_fidelity 标记（同 test_t24_migration_042）。
"""
import pytest
from sqlalchemy import create_engine, inspect as sa_inspect, text
from sqlalchemy.exc import IntegrityError

from conftest import mysql_fidelity_enabled
from test_alembic_baseline import _alembic_config, alembic_db_url  # noqa: F401 (fixture)

pytestmark = pytest.mark.mysql_fidelity

_BATCH_COLS = {
    "id", "origin", "status", "total_count", "succeeded_count", "failed_count",
    "skipped_count", "created_by", "tenant_id", "created_at", "finished_at",
}
_ITEM_COLS = {"id", "batch_id", "asset_type", "name", "status", "reason",
              "asset_id", "created_at"}


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


def _fks(url: str, table: str) -> dict[str, tuple[str, str]]:
    """权威口径：information_schema.DELETE_RULE（SQLAlchemy inspector 不回填 ondelete）"""
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT kcu.CONSTRAINT_NAME, rc.DELETE_RULE, kcu.REFERENCED_TABLE_NAME "
                "FROM information_schema.KEY_COLUMN_USAGE kcu "
                "JOIN information_schema.REFERENTIAL_CONSTRAINTS rc "
                "ON rc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA "
                "AND rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME "
                "WHERE kcu.TABLE_SCHEMA = DATABASE() AND kcu.TABLE_NAME = :t"), {"t": table})
            return {r[0]: (r[2], str(r[1]).upper()) for r in rows}
    finally:
        engine.dispose()


def test_migration_043_up_down_up_and_fk_semantics(alembic_db_url):  # noqa: F811 (fixture 注入)
    """042 → 043（head）→ 042 → 043：两表结构 + CASCADE/RESTRICT + 可重放。"""
    from alembic import command

    cfg = _alembic_config()

    # up（全链到 043 = head）
    command.upgrade(cfg, "head")
    assert _columns(alembic_db_url, "asset_import_batches") == _BATCH_COLS
    assert _columns(alembic_db_url, "asset_import_items") == _ITEM_COLS
    item_fks = _fks(alembic_db_url, "asset_import_items")
    assert item_fks["fk_import_items_batch"] == ("asset_import_batches", "CASCADE")
    assert item_fks["fk_import_items_asset"] == ("capability_assets", "RESTRICT")

    engine = create_engine(alembic_db_url)
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO capability_assets (asset_type, name, category, status, "
                "source_type, sync_state, listing_state, writable, created_at, updated_at) "
                "VALUES ('skill', 'mig-skill', 'uncategorized', 'experimental', "
                "'self_built', 'ok', 'unlisted', 1, NOW(), NOW())"))
            asset_id = conn.execute(text(
                "SELECT id FROM capability_assets WHERE name = 'mig-skill'")).scalar_one()
            conn.execute(text(
                "INSERT INTO asset_import_batches "
                "(origin, status, total_count, succeeded_count, created_by, created_at) "
                "VALUES ('file', 'completed', 1, 1, 'mig-root', NOW())"))
            batch_id = conn.execute(text(
                "SELECT id FROM asset_import_batches WHERE created_by = 'mig-root'"
            )).scalar_one()
            conn.execute(text(
                "INSERT INTO asset_import_items "
                "(batch_id, asset_type, name, status, asset_id, created_at) "
                "VALUES (:b, 'skill', 'mig-skill', 'succeeded', :a, NOW())"),
                {"b": batch_id, "a": asset_id})

        # CASCADE：批删除带走明细（组合子行，无独立生命周期）
        with engine.begin() as conn:
            conn.execute(text(
                "DELETE FROM asset_import_batches WHERE id = :b"), {"b": batch_id})
        with engine.begin() as conn:
            left = conn.execute(text("SELECT COUNT(*) FROM asset_import_items")).scalar_one()
            assert left == 0

        # RESTRICT：被明细引用的目录行不可物理删（provenance 回放链保链）
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO asset_import_batches "
                "(origin, status, created_by, created_at) "
                "VALUES ('file', 'running', 'mig-root-2', NOW())"))
            batch2 = conn.execute(text(
                "SELECT id FROM asset_import_batches WHERE created_by = 'mig-root-2'"
            )).scalar_one()
            conn.execute(text(
                "INSERT INTO asset_import_items (batch_id, asset_type, name, status, "
                "asset_id, created_at) VALUES (:b, 'skill', 'mig-skill', 'succeeded', "
                ":a, NOW())"), {"b": batch2, "a": asset_id})
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(text(
                    "DELETE FROM capability_assets WHERE id = :a"), {"a": asset_id})
        # 善后（隔离库）：先清明细再清资产，交还给 down
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM asset_import_items"))
            conn.execute(text("DELETE FROM asset_import_batches"))
            conn.execute(text(
                "DELETE FROM capability_assets WHERE id = :a"), {"a": asset_id})

        # down（单步回 042）：两表按建表逆序消失
        command.downgrade(cfg, "042")
        engine2 = create_engine(alembic_db_url)
        try:
            tables = set(sa_inspect(engine2).get_table_names())
        finally:
            engine2.dispose()
        assert "asset_import_batches" not in tables
        assert "asset_import_items" not in tables

        # up（再次到 head，可重放）
        command.upgrade(cfg, "head")
        assert _columns(alembic_db_url, "asset_import_items") == _ITEM_COLS
    finally:
        engine.dispose()
