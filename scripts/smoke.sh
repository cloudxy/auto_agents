#!/usr/bin/env bash
# 发布冒烟：健康检查可判退出码（G3 / S5）
set -euo pipefail
BASE="${SMOKE_BASE_URL:-http://127.0.0.1:9111}"
curl -fsS "${BASE}/api/v1/health/" | grep -q healthy
echo "smoke ok: ${BASE}/api/v1/health/"
