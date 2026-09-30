#!/usr/bin/env bash
# 空库引导：建库 → alembic upgrade head（种子随迁移写入）。幂等。
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

# 审计 BUG-41：只走迁移链。原先 create_all 建表后 stamp head，迁移里的种子数据
# （platform 租户、价目、角色 / 菜单等）一条都不会写入，新库缺种子、功能大面积空白。
# 空库 upgrade head 全链可用（test_alembic_baseline 覆盖）；已有库则只补未执行的迁移。
log "迁移链 upgrade head"
alembic upgrade head || die "upgrade head 失败"
log "完成。下一步：uv run python run.py"
