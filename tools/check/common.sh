#!/usr/bin/env bash
# 质量门禁公共：定位仓库根 + 违规计数（heredoc while 不进子 shell，避免假绿）
_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$_HERE/../.." && pwd)"
cd "$ROOT"

VIOLATIONS=0
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

report() {
    local rule="$1" detail="$2"
    echo -e "${RED}✗ [${rule}]${NC} ${detail}"
    VIOLATIONS=$((VIOLATIONS + 1))
}

report_lines() {
    while IFS='|' read -r rule detail; do
        [ -n "$rule" ] || continue
        report "$rule" "$detail"
    done <<EOF
$1
EOF
}
