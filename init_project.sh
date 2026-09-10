#!/usr/bin/env bash
# 项目初始化（新人第一次跑这个）。不生成骨架、不覆盖仓库文件。
#
#   bash init_project.sh
#   uv run python run.py setup
#
set -euo pipefail
. "$(cd "$(dirname "$0")" && pwd)/scripts/lib/common.sh"

ENV_FILE="$ROOT/config/${APP_ENV}/.env"

step() { log ""; log "==== $* ===="; }

install_tools() {
    step "1/6 工具"
    require_cmd git "https://git-scm.com/"
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv >/dev/null 2>&1; then
        log "安装 uv"
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    fi
    require_uv
    if ! uv python list 2>/dev/null | grep -q "3.13"; then
        log "安装 Python 3.13"
        uv python install 3.13
    fi
    if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
        if [[ "${OSTYPE:-}" == darwin* ]] && command -v brew >/dev/null 2>&1; then
            log "安装 Node.js"
            brew install node
        else
            die "请安装 Node.js 20：https://nodejs.org/"
        fi
    fi
    log "git $(git --version | awk '{print $3}')"
    log "$(uv --version)"
    log "node $(node --version)  npm $(npm --version)"
}

install_deps() {
    step "2/6 依赖"
    uv sync
    npm ci
    npm run build:shared
}

ensure_env() {
    step "3/6 本地密钥 ${ENV_FILE}"
    if [ -f "$ENV_FILE" ]; then
        log "已存在，跳过（不覆盖）"
        return
    fi
    mkdir -p "$(dirname "$ENV_FILE")"
    jwt="$(uv run python -c 'import secrets; print(secrets.token_urlsafe(48))')"
    hook="$(uv run python -c 'import secrets; print(secrets.token_urlsafe(48))')"
    cat > "$ENV_FILE" <<EOF
# 由 init_project.sh 生成，仅限本地。勿提交。
APP_ENV=${APP_ENV}
AUTO_AGENTS_MYSQL_DEFAULT_PASSWORD=123456
AUTO_AGENTS_REDIS_DEFAULT_PASSWORD=123456
AUTO_AGENTS_JWT__SECRET_KEY=${jwt}
AUTO_AGENTS_WEBHOOK__SECRET_KEY=${hook}
EOF
    log "已写入（MySQL/Redis 密码对齐 docker-compose 开发默认 123456）"
}

mysql_ok() {
    uv run python - <<'PY'
import os, sys, pymysql
from config import settings
c = settings.MYSQL.DEFAULT
pw = os.getenv("MYSQL_DEFAULT_PASSWORD") or str(settings.get("MYSQL_DEFAULT_PASSWORD", "") or "")
try:
    pymysql.connect(host=c.HOST, port=int(c.PORT), user=c.USER, password=pw, database=c.DB_NAME, charset="utf8mb4").close()
except Exception:
    try:
        pymysql.connect(host=c.HOST, port=int(c.PORT), user=c.USER, password=pw, charset="utf8mb4").close()
    except Exception:
        sys.exit(1)
PY
}

redis_ok() {
    uv run python - <<'PY'
import os, sys, redis
from config import settings
c = settings.REDIS.DEFAULT
pw = os.getenv("REDIS_DEFAULT_PASSWORD") or str(settings.get("REDIS_DEFAULT_PASSWORD", "") or "") or None
try:
    redis.Redis(host=c.HOST, port=int(c.PORT), password=pw, socket_timeout=2).ping()
except Exception:
    sys.exit(1)
PY
}

wait_infra() {
    local i=1
    while [ "$i" -le 45 ]; do
        if mysql_ok && redis_ok; then
            log "MySQL / Redis 已就绪"
            return 0
        fi
        i=$((i + 1))
        sleep 2
    done
    return 1
}

ensure_infra() {
    step "4/6 MySQL / Redis"
    if mysql_ok && redis_ok; then
        log "本机已可连，跳过"
        return
    fi
    require_cmd docker "本机没有可用的 MySQL/Redis。请启动数据库，或安装 Docker 后重跑。"
    log "docker compose up -d mysql redis"
    docker compose up -d mysql redis
    wait_infra || die "等待超时。检查：docker compose ps"
}

init_db() {
    step "5/6 数据库"
    bash "$ROOT/scripts/db/bootstrap.sh"
}

init_admin() {
    step "6/6 管理员"
    uv run python backend/scripts/set_admin_account.py
}

print_next() {
    log ""
    log "初始化完成。"
    log "  uv run python run.py          # 启动全部"
    log "  uv run python run.py status"
    log "后台 http://127.0.0.1:9112  账号 admin / 123456（登录后改密）"
    log "API  http://127.0.0.1:9111/docs"
}

install_tools
install_deps
ensure_env
ensure_infra
init_db
init_admin
print_next
