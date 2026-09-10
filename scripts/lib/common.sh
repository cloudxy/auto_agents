#!/usr/bin/env bash
# 公共：仓库根、日志、失败退出。仅供 init_project.sh 与 scripts/db/ 使用。
_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$_LIB/../.." && pwd)"
cd "$ROOT"
export APP_ENV="${APP_ENV:-local}"

log() { echo "[$(basename "$0")] $*"; }
die() { echo "[$(basename "$0")] $*" >&2; exit 1; }

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "未找到 $1。$2"
}

require_uv() {
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    require_cmd uv "安装：curl -LsSf https://astral.sh/uv/install.sh | sh"
}

alembic() {
    (cd "$ROOT/backend" && APP_ENV="${APP_ENV:-local}" uv run alembic -c alembic.ini "$@")
}
