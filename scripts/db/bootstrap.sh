#!/usr/bin/env bash
# 空库引导：建库 → create_all 基线 → stamp/upgrade head。幂等。
# 新环境也可直接 `bash scripts/db/migrate.sh`（002a 已补基线表）。
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$(cd "$(dirname "$0")/../lib" && pwd)/common.sh"

export APP_ENV="${APP_ENV:-local}"
require_uv

log "解析 MySQL（APP_ENV=${APP_ENV}）"
uv run python - <<'PY' || die "MySQL 连接/建库失败"
import os, sys
import pymysql
from config import settings

conf = settings.MYSQL.DEFAULT
password = os.getenv("MYSQL_DEFAULT_PASSWORD") or str(settings.get("MYSQL_DEFAULT_PASSWORD", ""))
host, port, db, user = conf.HOST, int(conf.PORT), conf.DB_NAME, conf.USER
try:
    pymysql.connect(host=host, port=port, user=user, password=password, database=db, charset="utf8mb4").close()
    print(f"[bootstrap-db] 数据库 {db} 已存在")
except pymysql.err.OperationalError as e:
    if e.args and e.args[0] == 1049:
        server = pymysql.connect(host=host, port=port, user=user, password=password, charset="utf8mb4")
        with server.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        server.commit(); server.close()
        print(f"[bootstrap-db] 已创建 {db}")
    else:
        print(e, file=sys.stderr); sys.exit(2)
PY

log "create_all 基线表"
uv run python scripts/db/init_tables.py || die "基线表失败"

log "迁移链收口"
CURRENT="$(alembic current 2>/dev/null || true)"
if echo "$CURRENT" | grep -qE '[0-9a-f]{12}'; then
    alembic upgrade head || die "upgrade head 失败"
else
    alembic stamp head || die "stamp head 失败"
fi
log "完成。下一步：uv run python run.py"
