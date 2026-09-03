#!/usr/bin/env bash
# ============================================================================
# check-frontend.sh — 前端工程门禁（工单 68，对齐 check-arch.sh 文化）
# 规则随批次启用（F-1~F-7 完整清单见 docs/plan/upgrade-2026-09-merged.md）
# 退出码 = 违规数
#
# 已启用：
#   F-2  错误提示统一：message.error 禁 instanceof/String(e)/response?.data 漂移写法
#   F-5  应用互引禁令：admin↔official 禁互引；shared 禁反向依赖应用
#   F-6  ApiEnvelope 单源：信封接口仅准 shared 定义，应用内禁重复声明
# 待启用（后续批次）：
#   F-7 .tsx ≤ 400 行（F-1 pages 禁直调 api 已由工单 71 承接，grep 验收）
# ============================================================================
set -u

VIOLATIONS=0
RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

report() {
    echo -e "${RED}✗ [$1]${NC} $2"
    VIOLATIONS=$((VIOLATIONS + 1))
}

# ── F-5 应用互引禁令 ──
f5() {
    # 相对路径跨应用（如 frontend/admin/src/x 引 ../../official/...）
    local hits
    hits=$(grep -rnE "from '[^']*/(admin|official)/src/" \
        "$ROOT/frontend/admin/src" "$ROOT/frontend/official/src" \
        --include="*.ts" --include="*.tsx" 2>/dev/null \
        | grep -vE "src/(admin|official)/[0-9A-Za-z_./-]*:[0-9]+:.*from '[^']*/(admin|official)/src/" \
        | grep -E "/(admin|official)/src/" || true)
    # 上行先全量匹配再剔除"同应用自身路径"（admin 文件引 admin 路径不违规）
    hits=$(grep -rnE "from '[^']*(\.\./)+((admin|official))/src/" \
        "$ROOT/frontend/admin/src" "$ROOT/frontend/official/src" \
        --include="*.ts" --include="*.tsx" 2>/dev/null | while IFS=: read -r file _rest; do
            app=$(echo "$file" | sed -E 's|.*/src/((admin|official))/src/.*|\1|')
            imported=$(echo "$_rest" | grep -oE "from '[^']*'" | grep -oE "(admin|official)/src/" | head -1 | cut -d/ -f1)
            [ -n "$imported" ] && [ "$imported" != "$app" ] && echo "$file:$_rest"
        done || true)
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        report "F-5" "应用互引（admin↔official 禁互引）: $line"
    done <<< "$hits"

    # shared 反向依赖应用
    local shared_hits
    shared_hits=$(grep -rnE "from '[^']*(frontend/(admin|official))" \
        "$ROOT/frontend/shared/src" --include="*.ts" --include="*.tsx" 2>/dev/null || true)
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        report "F-5" "shared 禁反向依赖应用: $line"
    done <<< "$shared_hits"
}

# ── F-6 ApiEnvelope 单源 ──
f6() {
    # 应用内禁止定义同构信封接口（定义 = interface/type + 名字 + <{；import 行排除）
    local defs
    defs=$(grep -rnE "(interface|type)\s+(ApiEnvelope|Envelope)\s*[<{=]" \
        "$ROOT/frontend/admin/src" "$ROOT/frontend/official/src" \
        --include="*.ts" --include="*.tsx" 2>/dev/null | grep -v "import" || true)
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        report "F-6" "信封接口须从 @auto-agents/frontend-shared 引入: $line"
    done <<< "$defs"

    # shared 内定义数必须为 1（防漂移重演）
    local shared_count
    shared_count=$(grep -rE "(interface|type)\s+ApiEnvelope\s*[<{]" \
        "$ROOT/frontend/shared/src" --include="*.ts" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$shared_count" -ne 1 ]; then
        report "F-6" "shared 内 ApiEnvelope 定义数 = $shared_count（应为 1）"
    fi
}

# ── F-2 错误提示统一：message.error 禁止漂移写法（须走 apiErrorMessage 提取后端 message）──
f2() {
    local hits
    hits=$(grep -rnE "message\.error\(.*(instanceof Error|String\(e\)|String\(err|response\?\.data)" \
        "$ROOT/frontend/admin/src" "$ROOT/frontend/official/src" \
        --include="*.ts" --include="*.tsx" 2>/dev/null | grep -v "\.test\." || true)
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        report "F-2" "错误提示漂移写法（改用 apiErrorMessage）: $line"
    done <<< "$hits"
}


# ── F-4 设计令牌黑名单：历史遗留色值禁入业务代码（改用 BRAND_TOKENS / --site-*）──
f4() {
    local hits
    hits=$(grep -rn "#1890ff" \
        "$ROOT/frontend/admin/src" "$ROOT/frontend/official/src" "$ROOT/frontend/shared/src" \
        --include="*.ts" --include="*.tsx" --include="*.css" 2>/dev/null         | grep -v "\.test\." | grep -vE '^[^:]+:[0-9]+:\s*(//|\*|#)' || true)
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        report "F-4" "历史遗留色值 #1890ff（改用 BRAND_TOKENS / var(--site-primary)）: $line"
    done <<< "$hits"
}


# ── F-3 轮询禁手写 setInterval（react-query refetchInterval 托管，自动 cleanup/失焦暂停）──
f3() {
    local hits
    hits=$(grep -rn "setInterval" \
        "$ROOT/frontend/admin/src" "$ROOT/frontend/official/src" \
        --include="*.ts" --include="*.tsx" 2>/dev/null \
        | grep -v "\.test\." | grep -v "clearInterval" || true)
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        report "F-3" "手写轮询（改 react-query refetchInterval）: $line"
    done <<< "$hits"
}


# ── F-7 大文件红线：业务 .tsx ≤ 400 行（超出即拆分）──
f7() {
    local hits
    hits=$(find "$ROOT/frontend/admin/src" "$ROOT/frontend/official/src" \
        -name "*.tsx" -not -name "*.test.tsx" 2>/dev/null \
        | while IFS= read -r f; do
            n=$(wc -l < "$f" | tr -d ' ')
            [ "$n" -gt 400 ] && echo "$f: $n 行"
          done)
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        report "F-7" ".tsx 超 400 行（须拆分）: $line"
    done <<< "$hits"
}

echo "前端工程门禁（F-2/F-3/F-4/F-5/F-6/F-7 已启用；F-1 批次 2 已由 service 归一承接）"
echo "=============================================================="

f2
f3
f4
f5
f6
f7

if [ $VIOLATIONS -eq 0 ]; then
    echo -e "${GREEN}✓ 前端工程门禁通过${NC}"
fi
exit $VIOLATIONS
