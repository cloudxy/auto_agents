#!/usr/bin/env bash
# ============================================================================
# 空库引导脚本（bootstrap-db）—— 兼容路径（E0.2 基线修复后非必需）
#
# 背景（docs/release-notes-2026-08-30.md「已知遗留项」留档）：
#   Alembic 迁移链 003/006 曾对链外表 spider_tasks 做 add_column（基线表由
#   scripts/init_db_sync.py 的 create_all 预建）——空库直接 `alembic upgrade head`
#   会因基线表缺失而失败，故有本脚本。
#   ⚠️ 该缺口已由 E0.2 修复（基线迁移 002a 补链外表，见
#   backend/alembic/versions/002a_baseline_spider_tasks_and_system_configs.py）：
#   新环境直接 `alembic upgrade head` 即可；本脚本保留为兼容路径，幂等可重复。
#
# 流程（幂等，可重复执行；每步失败即停并给出下一步提示）：
#   Step 1  前置校验（uv 可用）+ 解析 MySQL 连接参数并打印（密码掩码）
#   Step 2  连接测试 + 按需建库（CREATE DATABASE IF NOT EXISTS，utf8mb4）
#   Step 3  create_all 基线表（scripts/init_db_sync.py，已存在表自动跳过）
#   Step 4  迁移链收口：
#             alembic_version 缺失（create_all 基线）→ alembic stamp head
#             alembic_version 已存在               → alembic upgrade head
#                                                   （已在 head 则为 no-op）
#   Step 5  成功提示 + 下一步命令
#
# 用法：
#   bash scripts/bootstrap-db.sh               # 默认 APP_ENV=local
#   APP_ENV=dev bash scripts/bootstrap-db.sh   # 指定环境（local/dev/prod）
#
# 配置即代码红线：本脚本不硬编码任何连接串/密码/库名。参数取值优先级：
#   环境变量 MYSQL_DEFAULT_PASSWORD > Dynaconf settings（config/ 多层合并）
# alembic 连接串由 backend/alembic/env.py 从 settings 动态注入，与本脚本一致。
#
# 退出码：0 = 引导成功；非 0 = 失败（见各步 die 提示）
# ============================================================================
set -euo pipefail

# 定位仓库根目录（脚本所在目录的上一级）
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export APP_ENV="${APP_ENV:-local}"

log() { echo "[bootstrap-db] $*"; }
die() { echo "[bootstrap-db] ❌ $*" >&2; exit 1; }

# ---- Step 1: 前置校验 + 解析连接参数 ----
log "Step 1/4 解析 MySQL 连接参数（APP_ENV=${APP_ENV}；来源：环境变量 > Dynaconf）"
command -v uv >/dev/null 2>&1 \
    || die "未找到 uv，请先安装：https://docs.astral.sh/uv/"

# ---- Step 2: 连接测试 + 按需建库（Python 单块执行，避免 shell 引号陷阱）----
uv run python - <<'PY' || die "MySQL 连接/建库失败 —— 排查顺序：1) MySQL 服务是否可达（HOST/PORT）；2) MYSQL_DEFAULT_PASSWORD 环境变量或 config/${APP_ENV}/mysql.yml 凭据是否正确；3) 账号是否具备建库权限（受限账号请让 DBA 预建库后重跑本脚本）"
import os
import sys

import pymysql

from config import settings

conf = settings.MYSQL.DEFAULT
password = os.getenv('MYSQL_DEFAULT_PASSWORD') or str(settings.get('MYSQL_DEFAULT_PASSWORD', ''))
host, port, db, user = conf.HOST, int(conf.PORT), conf.DB_NAME, conf.USER
src = '环境变量 MYSQL_DEFAULT_PASSWORD' if os.getenv('MYSQL_DEFAULT_PASSWORD') else 'Dynaconf 配置'
print(f"[bootstrap-db] 目标：{user}@{host}:{port}/{db}（密码来源：{src}）")
print("[bootstrap-db] Step 1/4 连接参数校验通过")

try:
    # 直连目标库：成功 = 库已存在（幂等跳过建库）
    pymysql.connect(host=host, port=port, user=user, password=password, database=db, charset='utf8mb4').close()
    print(f"[bootstrap-db] Step 2/4 数据库 {db} 已存在，跳过建库")
except pymysql.err.OperationalError as e:
    errno = e.args[0] if e.args else None
    if errno == 1049:  # Unknown database → 服务端建库
        server = pymysql.connect(host=host, port=port, user=user, password=password, charset='utf8mb4')
        with server.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        server.commit()
        server.close()
        print(f"[bootstrap-db] Step 2/4 已创建数据库 {db}（utf8mb4 / utf8mb4_unicode_ci）")
    else:
        print(f"[bootstrap-db] MySQL 连接失败（errno={errno}）：{e}", file=sys.stderr)
        sys.exit(2)
PY

# ---- Step 3: create_all 基线表 ----
log "Step 3/4 create_all 基线表（scripts/init_db_sync.py，已存在表自动跳过）"
uv run python scripts/init_db_sync.py \
    || die "基线表创建失败 —— 上方 traceback 已含根因；修复后直接重跑本脚本（幂等）"

# ---- Step 4: 迁移链收口 ----
# alembic.ini 的 script_location 相对 backend/ 目录，必须 cd backend 执行
#（与 scripts/migrate.sh 同形态）。基线 create_all 后 alembic_version 缺失，
# 不可对空库 upgrade head（003/006 假定基线表已预建），须先 stamp。
log "Step 4/4 迁移链收口（backend/alembic，连接串由 env.py 从 settings 注入）"
ALEMBIC_CURRENT="$(cd backend && uv run alembic -c alembic.ini current 2>/dev/null || true)"
if echo "$ALEMBIC_CURRENT" | grep -qE '[0-9a-f]{12}'; then
    log "检测到已有迁移版本（$(echo "$ALEMBIC_CURRENT" | tail -n1 | sed 's/^ *//')）→ upgrade head（已在 head 则为 no-op）"
    (cd backend && uv run alembic -c alembic.ini upgrade head) \
        || die "upgrade head 失败 —— 检查 backend/alembic/versions 迁移链与库实际结构后重跑"
else
    log "未见 alembic_version（create_all 基线）→ stamp head（迁移链 003/006 假定基线表已预建，不可对空库 upgrade）"
    (cd backend && uv run alembic -c alembic.ini stamp head) \
        || die "stamp head 失败 —— 确认 Step 3 基线表已建出、backend/alembic 可用后重跑"
fi

# ---- Step 5: 完成 ----
log "✅ 引导完成：基线表已建、迁移链已收口（stamp/upgrade head）"
log "下一步：uv run python run.py backend   # 启动后端（端口 9111）"
log "详见 docs/database-bootstrap.md"
