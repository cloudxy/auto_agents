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
#   R1-R12  架构红线（配置/安全/反爬/模型/日志/异步 Redis/门面白名单）
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

echo "架构合规检查（13 条红线 + 3 条边界）"
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
# R7: API 层禁止 import ORM 模型（Router→Service→Repository→ORM 单向依赖）。
# 旧正则 `from.*\.models import` 匹配不到 `from platform_core.models.<子模块> import X`
# （模块路径以子模块名结尾而非 models），导致 API 层 ORM 直连漏检——本正则同时覆盖：
#   1) from <pkg>.models import X        （models 包直入）
#   2) from <pkg>.models.<sub> import X  （子模块，含相对导入 from .models import）
#   3) from <pkg>.models.<sub>.<sub2> import X（多级子模块）
#   4) 裸 import <pkg>.models[.<sub>]    （全限定名访问，同样泄漏 ORM）
# 扫描范围含 external_api/（同属 API 协议层）。
report "R7" "API 层 import models" \
    "$(grep -rnE "${GREP_EXCLUDES[@]}" \
        -e 'from +[a-zA-Z0-9_.]*\.models(\.[a-zA-Z0-9_]+)* +import' \
        -e '(^|[[:space:]])import +[a-zA-Z0-9_.]*\.models(\.[a-zA-Z0-9_]+)*([[:space:]]|$)' \
        backend/app/api/ backend/app/external_api/ 2>/dev/null || true)"

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
# 已知盲区：本 pattern 仅匹配链式 redis_client(...).method 写法；
# `r = redis_client("DEFAULT")` 两段式赋值不在覆盖内，靠人工评审把关
# （合规参照 backend/app/api/v2/health.py:39-40：先赋值再 await asyncio.to_thread(r.ping)）。
R11_OUTPUT="$(grep -rnE "${GREP_EXCLUDES[@]}" 'redis_client\([^)]*\)\.' backend/ 2>/dev/null || true)"
report "R11" "backend 同步 redis_client() 直调（阻塞事件循环）" "$R11_OUTPUT"

# --- 门面退役过渡（期 4 → S12 收口）---
# R12: 门面 import 白名单 —— backend/services/spider_service.py 为期 4 退役
# 过渡薄门面（__all__ 14 符号），API 域内已直连子 Service；本规则机械拦截
# 白名单外新增消费者（新代码必须直接依赖子 Service，不得绕回过渡门面）。
# 白名单（域外存量消费者，共 6 处；待全部迁移到子 Service 后，
# 本规则与门面一起删除）：
#   backend/tasks/consumer.py
#   backend/app/external_api/v1/public.py
#   backend/app/external_api/v1/webhooks.py
#   backend/app/api/v1/admin.py
#   backend/services/schedule_service.py
#   backend/services/ai_planner/__init__.py
# 注：backend/services/__init__.py 的 `from .spider_service import` 为门面
# 自身域内 re-export，相对导入不命中下方模式，无需豁免。
R12_OUTPUT="$(grep -rnE "${GREP_EXCLUDES[@]}" '(from backend\.services\.spider_service import|import backend\.services\.spider_service)' backend/ scrapy/ 2>/dev/null \
    | grep -vE '^backend/(tasks/consumer\.py|app/external_api/v1/(public|webhooks)\.py|app/api/v1/admin\.py|services/(schedule_service\.py|ai_planner/__init__\.py)):' || true)"
report "R12" "spider_service 门面白名单外 import（应直接依赖子 Service）" "$R12_OUTPUT"

# --- 租户过滤收口（SaaS S1）---
# R13: 业务查询必须经租户过滤收口（grep 补充手段；before_flush/do_orm_execute 主防线
# 见 platform_core/tenant_context.py）。机械约束三条：
# 1) platform_core/tenant_context.py 的事件安装调用（install_tenant_isolation）不得被移除——
#    backend/app/__init__.py 必须出现 platform_core 导入链（隔离随包导入自动安装）；
# 2) TenantMixin 模型的裸 Core 查询必须出现在 allowlist 声明的收口文件内
#    （tenant_context.py 自身 + 迁移），新增裸语句需在此登记并说明；
# 3) 豁免清单单一事实源同步（T8：租户豁免表外移）——事实源为
#    backend/app/tenant_isolation.py，本检查从事实源读取清单做双向校验（无第二份拷贝，
#    无双写漂移）：a. 组装点 create_app 内 setup_tenant_isolation 必须真实生效
#    （经 create_app() 后注册表应覆盖声明清单——组装断线即拦截）；
#    b. platform_core/tenant_context.py 不得回写清单内业务表名字面量（防硬编码回潮）。
R13_OUTPUT=""
if ! grep -q "from platform_core import tenant_context\|import platform_core.tenant_context\|from platform_core import.*tenant_context" backend/app/__init__.py platform_core/__init__.py 2>/dev/null; then
    R13_OUTPUT="platform_core/__init__.py 缺 tenant_context 安装导入（隔离钩子可能未安装）"
fi
# bash 3.2 兼容：命令替换 + heredoc（不用进程替换）；python 失败本身即违规（fail-loud）
R13_SYNC="$(uv run python - <<'PYEOF' 2>/dev/null || echo "R13 豁免同步校验执行失败（uv/python 环境）"
from backend.app import create_app

create_app()  # 显式经组装点（不依赖模块级 app 实例的存在）

import backend.app.tenant_isolation as ti
from platform_core import tenant_context as tc

problems = []
miss = set(ti.TENANT_EXEMPT_TABLES) - set(tc.tenant_exempt_tables())
if miss:
    problems.append(
        f"豁免表登记未生效（组装点 setup_tenant_isolation 断线？）: {sorted(miss)}")
miss = set(ti.PLATFORM_SHARED_READ_TABLES) - set(tc.platform_shared_read_tables())
if miss:
    problems.append(f"平台共享读表登记未生效: {sorted(miss)}")
src = open("platform_core/tenant_context.py", encoding="utf-8").read()
leak = [t for t in (*ti.TENANT_EXEMPT_TABLES, *ti.PLATFORM_SHARED_READ_TABLES)
        if '"%s"' % t in src]
if leak:
    problems.append(
        f"platform_core/tenant_context.py 回写业务表名（应走注册机制）: {leak}")
for p in problems:
    print(p)
PYEOF
)"
if [ -n "$R13_OUTPUT" ] && [ -n "$R13_SYNC" ]; then
    R13_OUTPUT="$R13_OUTPUT
$R13_SYNC"
elif [ -n "$R13_SYNC" ]; then
    R13_OUTPUT="$R13_SYNC"
fi
report "R13" "租户过滤收口（安装点/裸语句/豁免清单同步）" "$R13_OUTPUT"

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
    echo "✓ 架构合规检查通过（13 红线 + 3 边界，全部通过）"
    exit 0
else
    echo "共 $VIOLATIONS 处违规，请按 /check-arch Step 3 路由修复"
    [ "$VIOLATIONS" -gt 255 ] && VIOLATIONS=255
    exit "$VIOLATIONS"
fi
