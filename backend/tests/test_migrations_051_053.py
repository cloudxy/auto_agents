"""迁移 051（平台超管迁回 platform 租户）、052（orders.amount_sig）、053（中转日用量 + 令牌封禁原因）真库验证

隔离库（MYSQL_FIDELITY=1）：050 → 051；挂在 default 的超管迁回 platform、tenant_role 置空；
普通租户 admin 不动；downgrade 为 no-op（原归属不可还原）。
"""
import pytest
from sqlalchemy import create_engine, text

from conftest import mysql_fidelity_enabled
from test_alembic_baseline import _alembic_config, alembic_db_url  # noqa: F401 (fixture)

pytestmark = pytest.mark.mysql_fidelity


@pytest.fixture(autouse=True)
def _require_fidelity_mode():
    if not mysql_fidelity_enabled():
        pytest.skip("MYSQL_FIDELITY 未开启（迁移验证只在真实 MySQL 上跑）")


def test_migration_051_moves_platform_admin(alembic_db_url):  # noqa: F811
    from alembic import command

    cfg = _alembic_config()
    command.upgrade(cfg, "050")
    engine = create_engine(alembic_db_url)
    try:
        with engine.begin() as conn:
            # default 租户由迁移链种子，无需再插
            did = conn.execute(text("SELECT id FROM tenants WHERE slug='default'")).scalar_one()
            for name, plat in (("root51", 1), ("owner51", 0)):
                conn.execute(text(
                    "INSERT INTO users (username, email, password_hash, role, is_admin, is_active, "
                    "tenant_id, tenant_role, is_platform_admin, created_at, updated_at) "
                    "VALUES (:u, :e, 'x', 'admin', 1, 1, :t, 'admin', :p, NOW(), NOW())"),
                    {"u": name, "e": f"{name}@x.co", "t": did, "p": plat})
        command.upgrade(cfg, "051")
        with engine.connect() as conn:
            pid = conn.execute(text("SELECT id FROM tenants WHERE slug='platform'")).scalar_one()
            rows = {r.username: (r.tenant_id, r.tenant_role) for r in conn.execute(text(
                "SELECT username, tenant_id, tenant_role FROM users WHERE username IN ('root51','owner51')"))}
        assert rows["root51"] == (pid, None)
        assert rows["owner51"] == (did, "admin")
        command.downgrade(cfg, "050")  # no-op 可执行
        command.upgrade(cfg, "051")    # 幂等重放
    finally:
        engine.dispose()


def _simulate_042_contract_drift(conn) -> None:
    """复刻 dev 库实况：alive_flag 列在，但 042 的 contract 没落地（旧键仍在、新键缺失）"""
    conn.execute(text("ALTER TABLE users DROP INDEX uq_users_tenant_username_alive"))
    conn.execute(text("ALTER TABLE users DROP INDEX uq_users_email_alive"))
    conn.execute(text("ALTER TABLE users ADD CONSTRAINT uq_users_tenant_username UNIQUE (tenant_id, username)"))
    conn.execute(text("ALTER TABLE users ADD CONSTRAINT email UNIQUE (email)"))
    conn.execute(text("CREATE INDEX ix_users_email ON users (email)"))


def _user_keys(conn) -> dict[str, str]:
    return {r[0]: r[1] for r in conn.execute(text(
        "SELECT INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) "
        "FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'users' AND NON_UNIQUE = 0 GROUP BY INDEX_NAME"))}


def test_migration_050a_repairs_042_drift_then_051_moves_admin(alembic_db_url):  # noqa: F811
    """dev 库漂移：platform 租户里有已软删的同名 admin，旧键 (tenant_id, username) 不放行
    → 051 撞 1062。050a 自愈 042 的 contract 后，软删行脱离唯一判重，051 顺利迁回。"""
    from alembic import command

    cfg = _alembic_config()
    command.upgrade(cfg, "050")
    engine = create_engine(alembic_db_url)
    try:
        with engine.begin() as conn:
            _simulate_042_contract_drift(conn)
            did = conn.execute(text("SELECT id FROM tenants WHERE slug='default'")).scalar_one()
            pid = conn.execute(text("SELECT id FROM tenants WHERE slug='platform'")).scalar_one()
            conn.execute(text(
                "INSERT INTO users (username, email, password_hash, role, is_admin, is_active, tenant_id, "
                "tenant_role, is_platform_admin, deleted_at, created_at, updated_at) VALUES "
                "('admin', 'old-admin@x.co', 'x', 'admin', 1, 0, :p, NULL, 0, NOW(), NOW(), NOW()), "
                "('admin', 'admin@x.co', 'x', 'admin', 1, 1, :d, 'admin', 1, NULL, NOW(), NOW())"),
                {"p": pid, "d": did})
        command.upgrade(cfg, "051")
        with engine.connect() as conn:
            keys = _user_keys(conn)
            moved = conn.execute(text(
                "SELECT tenant_id, tenant_role FROM users WHERE email='admin@x.co'")).one()
            legacy_ix = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'users' AND INDEX_NAME = 'ix_users_email'")).scalar()
        assert keys.get("uq_users_tenant_username_alive") == "tenant_id,username,alive_flag"
        assert keys.get("uq_users_email_alive") == "email,alive_flag"
        assert "uq_users_tenant_username" not in keys and "email" not in keys
        assert legacy_ix == 0
        assert tuple(moved) == (pid, None)
        command.downgrade(cfg, "050")  # 050a / 051 均为 no-op 回滚
        command.upgrade(cfg, "051")    # 幂等重放
    finally:
        engine.dispose()


def test_migration_051_skips_live_username_collision(alembic_db_url):  # noqa: F811
    """platform 租户已有同名**存活**账号：051 不中断整条迁移链，跳过该超管（留给
    scripts/db/platform_admin_tenant.py inventory 人工处理），其余超管照常迁回"""
    from alembic import command

    cfg = _alembic_config()
    command.upgrade(cfg, "050")
    engine = create_engine(alembic_db_url)
    try:
        with engine.begin() as conn:
            did = conn.execute(text("SELECT id FROM tenants WHERE slug='default'")).scalar_one()
            pid = conn.execute(text("SELECT id FROM tenants WHERE slug='platform'")).scalar_one()
            conn.execute(text(
                "INSERT INTO users (username, email, password_hash, role, is_admin, is_active, tenant_id, "
                "tenant_role, is_platform_admin, created_at, updated_at) VALUES "
                "('dup51', 'dup51-p@x.co', 'x', 'admin', 1, 1, :p, NULL, 1, NOW(), NOW()), "
                "('dup51', 'dup51-d@x.co', 'x', 'admin', 1, 1, :d, 'admin', 1, NOW(), NOW()), "
                "('solo51', 'solo51@x.co', 'x', 'admin', 1, 1, :d, 'admin', 1, NOW(), NOW())"),
                {"p": pid, "d": did})
        command.upgrade(cfg, "051")
        with engine.connect() as conn:
            rows = {r.email: (r.tenant_id, r.tenant_role) for r in conn.execute(text(
                "SELECT email, tenant_id, tenant_role FROM users WHERE username IN ('dup51','solo51')"))}
        assert rows["dup51-d@x.co"] == (did, "admin")  # 撞名：原地不动
        assert rows["solo51@x.co"] == (pid, None)      # 不撞名：迁回
    finally:
        engine.dispose()


def test_migration_052_orders_amount_sig_up_down(alembic_db_url):  # noqa: F811
    """052：orders.amount_sig 可加可撤（审计 BUG-24 快照签名）"""
    from alembic import command
    from sqlalchemy import inspect as sa_inspect

    cfg = _alembic_config()
    command.upgrade(cfg, "052")
    engine = create_engine(alembic_db_url)
    try:
        cols = {c["name"] for c in sa_inspect(engine).get_columns("orders")}
        assert "amount_sig" in cols
        command.downgrade(cfg, "051")
        engine.dispose()
        cols = {c["name"] for c in sa_inspect(create_engine(alembic_db_url)).get_columns("orders")}
        assert "amount_sig" not in cols
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()


def test_migration_053_relay_usage_daily_up_down(alembic_db_url):  # noqa: F811
    """053：relay_usage_daily 表 + relay_tokens.blocked_reason 可加可撤，唯一键 (token, 日)"""
    from alembic import command
    from sqlalchemy import inspect as sa_inspect

    cfg = _alembic_config()
    command.upgrade(cfg, "053")
    engine = create_engine(alembic_db_url)
    try:
        insp = sa_inspect(engine)
        assert "relay_usage_daily" in insp.get_table_names()
        assert "blocked_reason" in {c["name"] for c in insp.get_columns("relay_tokens")}
        uniques = {u["name"]: u["column_names"] for u in insp.get_unique_constraints("relay_usage_daily")}
        assert uniques.get("uq_relay_usage_daily_token_date") == ["token_id", "stat_date"]
        command.downgrade(cfg, "052")
        engine.dispose()
        insp = sa_inspect(create_engine(alembic_db_url))
        assert "relay_usage_daily" not in insp.get_table_names()
        assert "blocked_reason" not in {c["name"] for c in insp.get_columns("relay_tokens")}
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()
