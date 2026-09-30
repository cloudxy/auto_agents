"""平台超管归属与 default 租户盘点（审计 R1-3 / B5-4 / P0-11a）

用法（仓库根目录）：
    uv run python scripts/db/platform_admin_tenant.py inventory [--env local]
    uv run python scripts/db/platform_admin_tenant.py apply --yes [--env local]

- inventory：只读。列出各租户、default 租户内的账号与业务数据量、不在 platform 租户下的平台超管。
- apply：把 is_platform_admin=1 且不在 platform 租户的账号迁回 platform 租户（tenant_role 置空），
  单事务执行；必须显式 --yes。迁移 051 做同一件事，本脚本供不便跑迁移的环境与事前演练。

背景：deps.py 的设计是平台超管挂 platform 租户；dev 库的超管 admin 挂在 default（id=1），
default 同时承接个人自助注册账号——该租户的 admin 可经成员接口触达超管（B1-1 已在服务层封堵），
租户停用也会连带锁死超管。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 每个业务表只统计 default 租户下的行数（表不存在时跳过）
_TENANT_TABLES = (
    "users", "spider_tasks", "spider_results", "spider_schedules", "spider_definitions",
    "ai_plans", "llm_providers", "api_keys", "orders", "capability_installs",
)


def _engine():
    from urllib.parse import quote_plus

    from sqlalchemy import create_engine

    from config import settings

    cfg = settings.MYSQL.DEFAULT
    pwd = os.getenv("MYSQL_DEFAULT_PASSWORD") or str(settings.get("MYSQL_DEFAULT_PASSWORD", "") or "")
    url = (f"mysql+pymysql://{cfg.USER}:{quote_plus(pwd)}@{cfg.HOST}:{cfg.PORT}/"
           f"{cfg.DB_NAME}?charset={cfg.get('CHARSET', 'utf8mb4')}")
    from platform_core.timeutil import MYSQL_UTC_CONNECT_ARGS

    return create_engine(url, pool_pre_ping=True, connect_args=dict(MYSQL_UTC_CONNECT_ARGS))


def inventory(conn) -> dict:
    from sqlalchemy import inspect, text

    tenants = [dict(r._mapping) for r in conn.execute(text(
        "SELECT id, slug, name, status FROM tenants ORDER BY id"))]
    print("== 租户 ==")
    for t in tenants:
        print(f"  #{t['id']:<4} {t['slug']:<24} {t['status']:<10} {t['name']}")
    default = next((t for t in tenants if t["slug"] == "default"), None)
    platform = next((t for t in tenants if t["slug"] == "platform"), None)
    report = {"default_id": default and default["id"], "platform_id": platform and platform["id"]}
    if default is not None:
        print(f"\n== default 租户 #{default['id']} 业务数据 ==")
        existing = set(inspect(conn).get_table_names())
        for table in _TENANT_TABLES:
            if table not in existing:
                continue
            n = conn.execute(text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :t"),
                             {"t": default["id"]}).scalar_one()
            print(f"  {table:<22} {n}")
        users = conn.execute(text(
            "SELECT id, username, role, tenant_role, is_platform_admin, is_active, deleted_at "
            "FROM users WHERE tenant_id = :t ORDER BY id"), {"t": default["id"]}).all()
        print(f"\n== default 租户账号（{len(users)}）==")
        for u in users:
            flag = " [平台超管]" if u.is_platform_admin else ""
            dead = " [已删]" if u.deleted_at else ""
            print(f"  #{u.id:<4} {u.username:<20} role={u.role:<9} tenant_role={u.tenant_role}{flag}{dead}")
    misplaced = conn.execute(text(
        "SELECT u.id, u.username, u.tenant_id, u.deleted_at IS NULL AS alive, "
        "EXISTS (SELECT 1 FROM users p JOIN tenants pt ON pt.id = p.tenant_id "
        "WHERE pt.slug = 'platform' AND p.username = u.username AND p.deleted_at IS NULL "
        "AND p.id <> u.id) AS clash "
        "FROM users u "
        "LEFT JOIN tenants t ON t.id = u.tenant_id "
        "WHERE u.is_platform_admin = 1 AND (t.slug IS NULL OR t.slug <> 'platform') "
        "ORDER BY u.id")).all()
    report["misplaced"] = [dict(r._mapping) for r in misplaced]
    print(f"\n== 不在 platform 租户的平台超管（{len(misplaced)}）==")
    for r in misplaced:
        clash = " [撞名：platform 租户已有同名存活账号，先改名]" if r.alive and r.clash else ""
        print(f"  #{r.id} {r.username} 当前 tenant_id={r.tenant_id}{clash}")
    if platform is None:
        print("\n!! 缺 platform 租户（迁移 024 未执行）")
    return report


def apply(conn, report: dict) -> int:
    from sqlalchemy import bindparam, text

    if not report.get("platform_id"):
        print("缺 platform 租户，拒绝执行")
        return 2
    # 撞名口径同迁移 051：存活且与 platform 租户（或本批先迁者）同名的跳过
    ids: list[int] = []
    claimed: set[str] = set()
    skipped: list[int] = []
    for r in report["misplaced"]:
        if r["alive"] and (r["clash"] or r["username"] in claimed):
            skipped.append(r["id"])
            continue
        if r["alive"]:
            claimed.add(r["username"])
        ids.append(r["id"])
    if skipped:
        print(f"撞名跳过（改名后重跑）: {skipped}")
    if not ids:
        print("无需迁移")
        return 1 if skipped else 0
    stmt = text(
        "UPDATE users SET tenant_id = :p, tenant_role = NULL "
        "WHERE is_platform_admin = 1 AND id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    conn.execute(stmt, {"p": report["platform_id"], "ids": ids})
    print(f"已迁回 platform 租户: {ids}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["inventory", "apply"])
    parser.add_argument("--env", default=None, help="透传为 APP_ENV（默认沿用当前环境）")
    parser.add_argument("--yes", action="store_true", help="apply 必须显式确认")
    args = parser.parse_args()
    if args.env:
        os.environ["APP_ENV"] = args.env
    engine = _engine()
    if args.action == "inventory":
        with engine.connect() as conn:
            inventory(conn)
            conn.rollback()
        return 0
    if not args.yes:
        print("apply 会修改数据库：请确认后加 --yes 重新执行")
        return 2
    with engine.begin() as conn:
        report = inventory(conn)
        return apply(conn, report)


if __name__ == "__main__":
    raise SystemExit(main())
