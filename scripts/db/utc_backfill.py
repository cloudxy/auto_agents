"""历史时间换算成 UTC（审计 BUG-43 一次性数据迁移）

用法（仓库根目录；**先停后端 / 消费者 / 爬虫**，换算期间不能有旧代码继续按本地时钟写入）：
    uv run python scripts/db/utc_backfill.py inventory [--env local]
    uv run python scripts/db/utc_backfill.py apply --yes [--env local] [--offset-minutes 480]

背景：旧代码有三套时钟——库默认值 / func.now() / ON UPDATE 取数据库会话时区（dev 库
SYSTEM=CST），少数 Python 写入用宿主本地 datetime.now()，其余 Python 写入是 UTC。
新约定是库里一律 UTC naive（platform_core/timeutil.py，会话固定 +00:00）。本脚本把
「旧时钟」列整体减去旧偏移，UTC 列不动：

- utc     ：Python 以 UTC 写入的列（代码逐一核对，见 UTC_COLUMNS），不动；
- legacy  ：库时钟 / 宿主本地时钟写入的列（created_at / updated_at / deleted_at 默认，
            以及 LEGACY_COLUMNS），减去偏移；
- tz      ：MySQL TIMESTAMP 类型（库内本就存 UTC，随会话时区换算），不动；
- unknown ：以上都不是。有数据的 unknown 列会让 apply 拒绝执行，先补分类再跑。

偏移取旧会话（不带 +00:00 的连接）下 NOW() 与 UTC_TIMESTAMP() 之差；宿主本地偏移与之
不一致时拒绝自动判断，需显式 --offset-minutes。偏移为 0（库与宿主本就是 UTC）时无事可做。
执行记录写进 system_configs 的 ops.clock_utc_backfill，重复执行会被拒绝（避免减两次）。
新代码已经跑过一段（会话 UTC 的写入已落库）时，用 --written-before 给出切换时刻（UTC），
之后的读数原样保留；inventory 会列出每列保留的行数供核对。
单事务：任何一步失败整体回滚。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MARKER_KEY = "ops.clock_utc_backfill"

# Python 以 UTC 写入（datetime.now(timezone.utc) / _utcnow() / 网关与爬虫的 UTC ISO），或是
# 前端以 toISOString() 提交后按 UTC 落库的输入值。依据见各写入点（2026-09-29 逐一核对）。
UTC_COLUMNS = frozenset({
    "product_events.occurred_at",                      # product_event_service._utcnow
    "orders.paid_at", "orders.late_notify_at", "orders.verified_at",
    "orders.fulfilled_at", "orders.unpaid_at",         # billing_service / payment_notify_service
    "tenant_subscriptions.current_period_end",         # billing_fulfill（UTC now 起算）
    "relay_sku_entitlements.activated_at", "relay_sku_entitlements.period_end",
    "relay_tokens.last_used_at", "relay_tokens.spend_synced_at",
    "relay_tokens.revoked_at", "relay_tokens.expires_at",
    "api_keys.expires_at", "api_keys.revoked_at", "api_keys.last_used_at",
    "outbound_keys.revoked_at",
    "users.last_login_at",                             # auth_service
    "tenants.expires_at",                              # billing_fulfill / 平台运营台（toISOString）
    "llm_provider_models.last_checked_at",
    "capability_assets.listed_at", "capability_assets.deleted_at",   # power_market _utcnow
    "capability_installs.deleted_at",                  # power_market/installs.py
    "capability_plugins.last_verified_at",
    "capability_sources.last_sync_at",
    "skill_jobs.finished_at",
    "skills.reviewed_at", "skills.imported_at",        # imported_at 是日历日（只按日期展示）
    "asset_import_batches.finished_at",
    "payment_channel_credentials.rotated_at",
    "workflow_instances.started_at", "workflow_instances.completed_at",
    "workflow_steps.started_at", "workflow_steps.completed_at",
    "spider_results.fetched_at",                       # scrapy 管道 UTC ISO
    "archive_records.retention_until",                 # retention_service
})

# 默认值 / func.now() / onupdate 之外、按旧时钟写入的列
LEGACY_COLUMNS = frozenset({
    "archive_records.archived_at",                     # server_default
    "skill_jobs.started_at",                           # server_default
    "spider_tasks.started_at", "spider_tasks.completed_at",   # func.now()
    "spider_schedules.last_run_at", "spider_schedules.next_run_at",  # 旧 datetime.now()
    "alert_rules.last_triggered_at",                   # 旧 datetime.now()
})
LEGACY_BY_NAME = frozenset({"created_at", "updated_at", "deleted_at"})


def classify(table: str, column: str, data_type: str) -> str:
    key = f"{table}.{column}"
    if data_type == "timestamp":
        return "tz"
    if key in UTC_COLUMNS:
        return "utc"
    if key in LEGACY_COLUMNS or column in LEGACY_BY_NAME:
        return "legacy"
    return "unknown"


def _url() -> str:
    from config import settings

    cfg = settings.MYSQL.DEFAULT
    pwd = os.getenv("MYSQL_DEFAULT_PASSWORD") or str(settings.get("MYSQL_DEFAULT_PASSWORD", "") or "")
    return (f"mysql+pymysql://{cfg.USER}:{quote_plus(pwd)}@{cfg.HOST}:{cfg.PORT}/"
            f"{cfg.DB_NAME}?charset={cfg.get('CHARSET', 'utf8mb4')}")


def detect_offsets(legacy_conn) -> tuple[int, int]:
    """(旧会话库时钟偏移, 宿主本地偏移)，单位分钟"""
    from sqlalchemy import text

    db_minutes = int(legacy_conn.execute(text("SELECT TIMESTAMPDIFF(MINUTE, UTC_TIMESTAMP(), NOW())")).scalar())
    host = datetime.now().astimezone().utcoffset()
    host_minutes = int(host.total_seconds() // 60) if host is not None else 0
    return db_minutes, host_minutes


def load_columns(conn) -> list[dict]:
    from sqlalchemy import text

    rows = conn.execute(text(
        "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, EXTRA FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND DATA_TYPE IN ('datetime', 'timestamp') "
        "AND TABLE_NAME <> 'alembic_version' ORDER BY TABLE_NAME, ORDINAL_POSITION"
    )).all()
    out = []
    for table, column, data_type, extra in rows:
        n, lo, hi = conn.execute(text(
            f"SELECT COUNT(`{column}`), MIN(`{column}`), MAX(`{column}`) FROM `{table}`")).one()
        out.append({
            "table": table, "column": column, "type": data_type,
            "on_update": "on update" in str(extra or "").lower(),
            "kind": classify(table, column, data_type), "n": int(n or 0), "min": lo, "max": hi,
        })
    return out


def read_marker(conn):
    from sqlalchemy import text

    return conn.execute(text("SELECT config_value FROM system_configs WHERE config_key = :k"),
                        {"k": MARKER_KEY}).scalar()


def event_skew_minutes(conn):
    """埋点自检：occurred_at（UTC）与 created_at（库时钟）平均差，换算后应≈0"""
    from sqlalchemy import text

    return conn.execute(text(
        "SELECT AVG(TIMESTAMPDIFF(MINUTE, occurred_at, created_at)) FROM product_events")).scalar()


def inventory(conn, offset: int, cutoff: datetime | None = None) -> list[dict]:
    from datetime import timedelta

    from sqlalchemy import text

    cols = load_columns(conn)
    if cutoff is not None:
        for c in cols:
            if c["kind"] == "legacy" and c["n"]:
                c["after_cutoff"] = int(conn.execute(text(
                    f"SELECT COUNT(*) FROM `{c['table']}` WHERE `{c['column']}` >= :b"), {"b": cutoff}).scalar())
    print(f"旧时钟偏移: {offset} 分钟；标记: {read_marker(conn) or '未执行'}")
    print(f"埋点自检（occurred_at vs created_at 平均差，分钟）: {event_skew_minutes(conn)}")
    for kind in ("legacy", "utc", "tz", "unknown"):
        group = [c for c in cols if c["kind"] == kind and c["n"]]
        print(f"\n== {kind}（有数据 {len(group)} 列）==")
        for c in group:
            shift = timedelta(minutes=offset) if kind == "legacy" else timedelta(0)
            kept = c.get("after_cutoff")
            print(f"  {c['table']}.{c['column']:<24} n={c['n']:<5} {c['min']} .. {c['max']}"
                  + (f"  → {c['min'] - shift} .. {c['max'] - shift}" if shift else "")
                  + (f"  [cutoff 之后已是 UTC，保留 {kept} 行]" if kept else ""))
    empty_unknown = [f"{c['table']}.{c['column']}" for c in cols if c["kind"] == "unknown" and not c["n"]]
    if empty_unknown:
        print(f"\n（无数据的 unknown 列，不影响执行）: {', '.join(empty_unknown)}")
    return cols


def build_statements(cols: list[dict], offset: int, cutoff: datetime | None = None) -> list[str]:
    """每表一条 UPDATE；表里有 ON UPDATE 列而它不在换算集合时显式 col = col，防止被刷成 NOW()。

    cutoff：新代码（会话 UTC）开始写库的时刻（UTC 读数）。读数 >= cutoff 的行已是 UTC，原样保留。
    前提是切换前 offset 时长内没有旧时钟写入（两类读数不重叠）——inventory 会列出 cutoff 之后的
    行数供核对。
    """
    by_table: dict[str, list[dict]] = {}
    for c in cols:
        by_table.setdefault(c["table"], []).append(c)
    stmts = []
    for table, tcols in sorted(by_table.items()):
        shift = [c["column"] for c in tcols if c["kind"] == "legacy" and c["n"]]
        if not shift:
            continue
        minus = f"INTERVAL {int(offset)} MINUTE"
        if cutoff is None:
            sets = [f"`{c}` = `{c}` - {minus}" for c in shift]
        else:
            bound = cutoff.strftime("%Y-%m-%d %H:%M:%S")  # datetime 格式化，无注入面
            sets = [f"`{c}` = IF(`{c}` < '{bound}', `{c}` - {minus}, `{c}`)" for c in shift]
        sets += [f"`{c['column']}` = `{c['column']}`" for c in tcols
                 if c["on_update"] and c["column"] not in shift]
        stmts.append(f"UPDATE `{table}` SET {', '.join(sets)}")
    return stmts


def apply(conn, cols: list[dict], offset: int, cutoff: datetime | None = None) -> int:
    from sqlalchemy import text

    if read_marker(conn):
        print("已执行过（system_configs 有标记），拒绝重复换算")
        return 2
    unknown = [f"{c['table']}.{c['column']}" for c in cols if c["kind"] == "unknown" and c["n"]]
    if unknown:
        print(f"有数据的未分类列，先在脚本里补分类: {unknown}")
        return 2
    stmts = build_statements(cols, offset, cutoff)
    for s in stmts:
        conn.execute(text(s))
    conn.execute(text(
        "INSERT INTO system_configs (config_key, config_value, description, updated_at) "
        "VALUES (:k, :v, :d, UTC_TIMESTAMP())"
    ), {"k": MARKER_KEY, "d": "BUG-43 历史时间换算 UTC 的执行记录（勿删：防重复换算）",
        "v": json.dumps({"offset_minutes": offset, "tables": len(stmts),
                         "written_before": cutoff.isoformat() if cutoff else None,
                         "applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})})
    print(f"已换算 {len(stmts)} 张表（偏移 {offset} 分钟）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["inventory", "apply"])
    parser.add_argument("--env", default=None, help="透传为 APP_ENV（默认沿用当前环境）")
    parser.add_argument("--yes", action="store_true", help="apply 必须显式确认")
    parser.add_argument("--offset-minutes", type=int, default=None,
                        help="旧时钟相对 UTC 的偏移（分钟）；缺省自动探测")
    parser.add_argument("--written-before", default=None,
                        help="新代码开始写库的时刻（UTC 读数，如 2026-09-29T01:00:00）；之后的行已是 UTC，不换算")
    args = parser.parse_args()
    if args.env:
        os.environ["APP_ENV"] = args.env
    cutoff = datetime.fromisoformat(args.written_before) if args.written_before else None
    if cutoff is not None and cutoff.tzinfo is not None:
        cutoff = cutoff.astimezone(timezone.utc).replace(tzinfo=None)

    from sqlalchemy import create_engine

    from platform_core.timeutil import MYSQL_UTC_CONNECT_ARGS

    url = _url()
    legacy_engine = create_engine(url)  # 刻意不带 +00:00：探测旧会话时区
    with legacy_engine.connect() as conn:
        db_offset, host_offset = detect_offsets(conn)
    legacy_engine.dispose()
    offset = args.offset_minutes
    if offset is None:
        if db_offset != host_offset:
            print(f"库时钟偏移 {db_offset} 与宿主偏移 {host_offset} 不一致，请用 --offset-minutes 指定")
            return 2
        offset = db_offset
    engine = create_engine(url, connect_args=dict(MYSQL_UTC_CONNECT_ARGS))
    if args.action == "inventory":
        with engine.connect() as conn:
            inventory(conn, offset, cutoff)
            conn.rollback()
        return 0
    if offset == 0:
        print("旧时钟就是 UTC，无需换算")
        return 0
    if not args.yes:
        print("apply 会修改数据库：请先 inventory 核对，再加 --yes 重新执行")
        return 2
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            cols = inventory(conn, offset, cutoff)
            code = apply(conn, cols, offset, cutoff)
            if code:
                trans.rollback()
                return code
            print(f"换算后埋点自检（分钟）: {event_skew_minutes(conn)}")
            trans.commit()
        except Exception:
            trans.rollback()
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
