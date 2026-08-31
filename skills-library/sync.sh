#!/usr/bin/env bash
# 总入口：遍历 manifests/，调用对应 adapters/ 把 skill 发布到各工具。
# 用法:
#   ./sync.sh              仅同步所有已知适配器
#   ./sync.sh --reindex     同步后重建 index/index.db
#   ./sync.sh --serve       同步后启动本地管理后台 (backend/app.py)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# 优先用 auto_agents 根 .venv（uv workspace，已含 PyYAML/FastAPI/uvicorn），
# 其次本目录 .venv，最后退回系统 python3。
PROJECT_ROOT="$(cd "$ROOT/.." && pwd)"
if [[ -x "$PROJECT_ROOT/.venv/bin/python3" ]]; then
  PYTHON="$PROJECT_ROOT/.venv/bin/python3"
elif [[ -x "$ROOT/.venv/bin/python3" ]]; then
  PYTHON="$ROOT/.venv/bin/python3"
else
  PYTHON="python3"
fi

echo "== syncing skills-library ($ROOT) =="

for adapter in "$ROOT"/adapters/*.sh; do
  [[ -f "$adapter" ]] || continue
  tool="$(basename "$adapter" .sh)"
  echo "-- $tool --"
  bash "$adapter" "$ROOT"
done

for arg in "$@"; do
  case "$arg" in
    --reindex)
      echo "== rebuilding index =="
      "$PYTHON" "$ROOT/index/build_index.py" "$ROOT"
      ;;
    --serve)
      echo "== rebuilding index =="
      "$PYTHON" "$ROOT/index/build_index.py" "$ROOT"
      echo "== starting backend =="
      exec "$PYTHON" "$ROOT/backend/app.py" "$ROOT"
      ;;
    *)
      echo "unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

echo "== done =="
