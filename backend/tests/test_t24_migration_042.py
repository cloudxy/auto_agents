"""T-24 迁移 042 可逆性 + 在册唯一键语义：users.alive_flag 唯一键在册化。

db-spec §16.1：up → down → up 三连在隔离库（真实 MySQL，MYSQL_FIDELITY=1）
跑并退出码 0；down 带 impossible-down 前置校验（025 同款）；生产禁止
downgrade past 037，本文件只在隔离库验证。默认 SQLite 会话跑不了迁移链
（方言差异），全部 mysql_fidelity 标记。
"""
import pytest
from sqlalchemy import create_engine, inspect as sa_inspect, text
from sqlalchemy.exc import IntegrityError

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
        return {c["name"] for c in sa_inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


def _unique_indexes(url: str, table: str) -> dict[str, list[str]]:
    engine = create_engine(url)
    try:
        return {
            ix["name"]: ix["column_names"]
            for ix in sa_inspect(engine).get_indexes(table)
            if ix.get("unique")
        }
    finally:
        engine.dispose()


def _plain_indexes(url: str, table: str) -> set[str]:
    engine = create_engine(url)
    try:
        return {ix["name"] for ix in sa_inspect(engine).get_indexes(table)
                if not ix.get("unique")}
    finally:
        engine.dispose()


def test_migration_042_up_down_up_and_alive_semantics(alembic_db_url):  # noqa: F811 (fixture 注入)
    """041 → 042 → 041 → 042：结构换防 + 在册唯一/释放/恢复撞键 + impossible-down。"""
    from alembic import command

    cfg = _alembic_config()

    # up（全链到 042）
    command.upgrade(cfg, "head")
    assert "alive_flag" in _columns(alembic_db_url, "users")
    uniques = _unique_indexes(alembic_db_url, "users")
    assert uniques.get("uq_users_tenant_username_alive") == [
        "tenant_id", "username", "alive_flag"]
    assert uniques.get("uq_users_email_alive") == ["email", "alive_flag"]
    assert "uq_users_tenant_username" not in uniques  # 旧键已撤
    assert "email" not in uniques  # 001 部署自动名唯一键已撤（按 information_schema 定位）
    plain = _plain_indexes(alembic_db_url, "users")
    assert "ix_users_email" not in plain  # 纯重复索引已撤（026 口径不恢复）
    assert "ix_users_username" in plain  # 跨租户 username 消歧索引保留（db-spec §8）

    # 在册唯一语义（MySQL 8 真库）：同键「一活一删」合法（释放，GWT-93.5/93.7）
    engine = create_engine(alembic_db_url)
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO tenants (slug, name, status, created_at, updated_at) "
                "VALUES ('t24-mig', '迁移验证', 'active', NOW(), NOW())"))
            tid = conn.execute(text(
                "SELECT id FROM tenants WHERE slug = 't24-mig'")).scalar_one()
            conn.execute(text(
                "INSERT INTO users (username, email, password_hash, is_active, "
                "is_admin, tenant_id, is_platform_admin, role, created_at, updated_at) "
                "VALUES ('mig-name', 'a@t24.local', 'x', 1, 0, :tid, 0, 'viewer', NOW(), NOW())"),
                {"tid": tid})
            # 已删行同 username 同租户：alive_flag=NULL 脱离唯一 → 放行（软删释放）
            conn.execute(text(
                "INSERT INTO users (username, email, password_hash, is_active, "
                "is_admin, tenant_id, is_platform_admin, role, deleted_at, created_at, updated_at) "
                "VALUES ('mig-name', 'b@t24.local', 'x', 0, 0, :tid, 0, 'viewer', NOW(), NOW(), NOW())"),
                {"tid": tid})

        # 恢复撞键兜底：清 deleted_at 使 alive_flag=1 → 1062（db-spec §16.1 串行序安全）
        with pytest.raises(IntegrityError) as exc_info:
            with engine.begin() as conn:
                conn.execute(text(
                    "UPDATE users SET deleted_at = NULL, is_active = 1 "
                    "WHERE email = 'b@t24.local'"))
        assert "1062" in str(exc_info.value.orig)

        # down（单步回 041）——impossible-down：同键多行（一活一删）→ 显式 raise
        with pytest.raises(RuntimeError, match="同名多行"):
            command.downgrade(cfg, "041")
        assert "uq_users_tenant_username_alive" in _unique_indexes(alembic_db_url, "users")

        # 测试善后（仅隔离库）：物理清掉软删同名行，使旧键可重建后完成 down→up
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE email = 'b@t24.local'"))
        command.downgrade(cfg, "041")
        assert "alive_flag" not in _columns(alembic_db_url, "users")
        uniques_after = _unique_indexes(alembic_db_url, "users")
        assert uniques_after.get("uq_users_tenant_username") == ["tenant_id", "username"]
        assert "email" in uniques_after  # 001 自动名形态恢复
        assert "ix_users_email" not in _plain_indexes(alembic_db_url, "users")  # 不恢复（026 口径）

        # up（再次到 042，可重放）
        command.upgrade(cfg, "head")
        assert "alive_flag" in _columns(alembic_db_url, "users")
        assert "uq_users_email_alive" in _unique_indexes(alembic_db_url, "users")
    finally:
        engine.dispose()
