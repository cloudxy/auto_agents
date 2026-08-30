#!/usr/bin/env bash
# 架构合规检查 - project_rule.md 架构红线 + 核心代码边界的机械化扫描
#
# 用法：
#   bash scripts/check-arch.sh          # 从任意目录调用（自动定位仓库根）
#
# 退出码：0 = 全部通过；非 0 = 违规总数（上限 255）
# 与 /check-arch Skill 的检查命令保持一致，供 pre-commit 与 CI 复用。
#
# 规则分两组：
#   R1-R11  架构红线（配置/安全/反爬/模型/日志/异步 Redis）
#   B1-B3   核心代码边界（模块依赖方向）

set -uo pipefail

# 定位仓库根目录（脚本所在目录的上一级）
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VIOLATIONS=0

# 排除缓存/构建产物目录，避免二进制文件噪音（对齐 git ls-files 范围）
GREP_EXCLUDES=(--exclude-dir=__pycache__ --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=runtime --exclude-dir=logs)

report() {
    # report <规则号> <描述> <输出>
    local rule="$1" desc="$2" output="$3"
    if [ -n "$output" ]; then
        echo "❌ $rule: $desc"
        echo "$output"
        echo ""
        VIOLATIONS=$((VIOLATIONS + $(echo "$output" | wc -l | tr -d ' ')))
    else
        echo "✓ $rule: $desc"
    fi
}

echo "架构合规检查（11 条红线 + 3 条边界）"
echo "======================================"

# --- 配置即代码 ---
report "R1" "硬编码连接串" \
    "$(grep -rnE "${GREP_EXCLUDES[@]}" '(mysql|postgres|redis)://[^\$\{]' backend/ scrapy/ 2>/dev/null | grep -vE '\.env\.example|README' || true)"

report "R2" "明文 password" \
    "$(grep -rnE "${GREP_EXCLUDES[@]}" 'password\s*=\s*"[^$]' backend/ scrapy/ 2>/dev/null | grep -vE 'example|test_' || true)"

# --- 爬取与存储分离 ---
report "R3" "scrapy → backend 反向依赖" \
    "$(grep -rnE "${GREP_EXCLUDES[@]}" '^(from|import) (backend|app)\.' scrapy/ 2>/dev/null || true)"

report "R4" "scrapy 使用 SQLAlchemy" \
    "$(grep -rnE "${GREP_EXCLUDES[@]}" 'from sqlalchemy|SessionLocal|mysql_session|get_async_db' scrapy/ 2>/dev/null || true)"

# --- 反爬是底线 ---
if grep -qE 'DOWNLOAD_DELAY' scrapy/settings.py 2>/dev/null; then
    echo "✓ R5: DOWNLOAD_DELAY 已配置"
else
    echo "❌ R5: 缺失 DOWNLOAD_DELAY（scrapy/settings.py）"
    VIOLATIONS=$((VIOLATIONS + 1))
fi

if grep -rqE "${GREP_EXCLUDES[@]}" 'USER_AGENT|UserAgentMiddleware' scrapy/ 2>/dev/null; then
    echo "✓ R6: USER_AGENT 配置存在"
else
    echo "❌ R6: 缺失 USER_AGENT 配置"
    VIOLATIONS=$((VIOLATIONS + 1))
fi

# --- 模型即契约 ---
report "R7" "API 层 import models" \
    "$(grep -rnE "${GREP_EXCLUDES[@]}" 'from.*\.models import' backend/app/api/ 2>/dev/null || true)"

report "R8" "models 反向 import schemas" \
    "$(grep -rnE "${GREP_EXCLUDES[@]}" 'from.*\.schemas import' platform_core/models/ 2>/dev/null || true)"

# --- 数据流向不可逆 ---
R9_OUTPUT="$(uv run python -c 'import backend.app' 2>&1 | grep -iE 'circular|cannot import name' || true)"
if [ -n "$R9_OUTPUT" ]; then
    echo "❌ R9: 循环 import"
    echo "$R9_OUTPUT"
    VIOLATIONS=$((VIOLATIONS + 1))
else
    echo "✓ R9: 无循环 import"
fi

# --- 日志即证据 ---
R10_OUTPUT=""
for f in backend/services/*.py; do
    [ -e "$f" ] || continue
    FOUND="$(awk '/^(async )?def [a-z]/ {name=$0; getline; if ($0 !~ /logger\./) print FILENAME":"NR-1": "name}' "$f" 2>/dev/null || true)"
    if [ -n "$FOUND" ]; then
        R10_OUTPUT="${R10_OUTPUT}${FOUND}
"
    fi
done
report "R10" "service 方法入口缺 logger" "${R10_OUTPUT%$'\n'}"

# --- 异步 Redis 收口（期 3 → 期 4 全域生效）---
# R11: async 上下文禁止同步 redis_client() 链式直调（网络 IO 阻塞事件循环）。
# 期 4 豁免清零：原行内豁免（spider_service._task_log_offset）与文件级豁免
# （spider_query_service.py）均已异步化（get_async_redis + await），无残留。
R11_OUTPUT="$(grep -rnE "${GREP_EXCLUDES[@]}" 'redis_client\([^)]*\)\.' backend/ 2>/dev/null || true)"
report "R11" "backend 同步 redis_client() 直调（阻塞事件循环）" "$R11_OUTPUT"

# --- 核心代码边界（模块依赖方向） ---
echo ""
echo "--- 核心代码边界 ---"

# B1: platform_core 只依赖 config，禁止反向依赖 backend / scrapy
report "B1" "platform_core → backend/scrapy 反向依赖" \
    "$(grep -rnE "${GREP_EXCLUDES[@]}" '^(from|import) (backend|scrapy)' platform_core/ 2>/dev/null || true)"

# B2: backend 禁止直接 import scrapy（应通过 Redis 队列 / API 解耦）
report "B2" "backend → scrapy 直接依赖" \
    "$(grep -rnE "${GREP_EXCLUDES[@]}" '^(from|import) scrapy' backend/ 2>/dev/null || true)"

# B3: config 是最底层，禁止 import 任何业务模块
report "B3" "config → 业务模块反向依赖" \
    "$(grep -rnE "${GREP_EXCLUDES[@]}" '^(from|import) (backend|scrapy|platform_core)' config/ 2>/dev/null || true)"

# --- 汇总 ---
echo ""
if [ "$VIOLATIONS" -eq 0 ]; then
    echo "✓ 架构合规检查通过（11 红线 + 3 边界，全部通过）"
    exit 0
else
    echo "共 $VIOLATIONS 处违规，请按 /check-arch Step 3 路由修复"
    [ "$VIOLATIONS" -gt 255 ] && VIOLATIONS=255
    exit "$VIOLATIONS"
fi
