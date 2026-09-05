#!/usr/bin/env bash
# ============================================================================
# check-db-ir.sh — DBML IR 静态 lint（D 线 D2，ADR-0002 执法面）
# 规则来源：atlas lint 规则清单 + schemalint + sqlcheck 语义精选
# 退出码 = 违规数（超过 255 截断为 255）；无 *.dbml 文件时静默通过（不阻塞非 DB 改动）
#
# 2026-09 T2 修复：R-NAM / R-AUD / R-ENUM 原为 `检测器 | while read; do report; done`
# 管道结构，report() 的 VIOLATIONS 自增发生在管道子 shell 无法传回主 shell，
# 有违规仍 exit 0 假绿。现改为「命令替换捕获检测输出 + report_lines 以 heredoc
# 喂 while」（bash 3.2 兼容，不依赖进程替换）。
# 检测输出协议：逐行打印 `规则ID|明细`，由 report_lines 在主 shell 计数。
# ============================================================================

set -u

VIOLATIONS=0
RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'

report() {
    local rule="$1" detail="$2"
    echo -e "${RED}✗ [${rule}]${NC} ${detail}"
    VIOLATIONS=$((VIOLATIONS + 1))
}

# report_lines <检测器多行输出>：在当前 shell 内逐行解析并计数。
# 关键：heredoc 方式的 while 循环不进子 shell，VIOLATIONS 自增可传回主 shell。
report_lines() {
    while IFS='|' read -r rule detail; do
        [ -n "$rule" ] || continue
        report "$rule" "$detail"
    done <<EOF
$1
EOF
}

# 收集 DBML 文件
DBML_FILES=$(find . -name "*.dbml" -not -path "./.venv/*" -not -path "./node_modules/*" 2>/dev/null)

if [ -z "$DBML_FILES" ]; then
    # 无 DBML → 检查 alembic/versions 是否有增量破坏性变更（作为兜底）
    if [ -d backend/alembic/versions ]; then
        echo "check-db-ir: 无 DBML 文件，跳过 IR lint（迁移 lint 由 check-db-migrations 覆盖）"
    fi
    exit 0
fi

DBML_COUNT=$(printf '%s\n' "$DBML_FILES" | grep -c .)
echo "DBML IR 静态 lint（${DBML_COUNT} 个文件）"
echo "=================================="

for f in $DBML_FILES; do
    # R-NAM: 表名 snake_case 复数
    RNAM_OUT=$(grep -E 'Table [a-z]+[^s{]' "$f" 2>/dev/null | while IFS= read -r line; do
        table_name=$(echo "$line" | sed 's/Table \([a-z_]*\).*/\1/')
        if ! echo "$table_name" | grep -qE '^[a-z]+(_[a-z]+)*s$'; then
            echo "R-NAM|$f: 表名 '$table_name' 应为 snake_case 复数（如 spider_tasks）"
        fi
    done)
    report_lines "$RNAM_OUT"

    # R-AUD: 审计字段（created_at + updated_at 必备）
    RAUD_OUT=$(python3 -c '
import re, sys
path = sys.argv[1]
try:
    content = open(path).read()
except OSError:
    sys.exit(0)
tables = re.findall(r"Table\s+(\w+)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}", content, re.DOTALL)
for name, body in tables:
    if "created_at" not in body:
        print(f"R-AUD|{path}: 表 {name} 缺 created_at 审计字段")
    if "updated_at" not in body:
        print(f"R-AUD|{path}: 表 {name} 缺 updated_at 审计字段")
' "$f" 2>/dev/null || true)
    report_lines "$RAUD_OUT"

    # R-FK: Ref 声明引用完整性
    grep -q "Ref:" "$f" 2>/dev/null || report "R-FK" "$f: 零 Ref 声明（单表设计或缺失关系？）"

    # R-IDX: 有查询模式声明的表应有索引注释
    if grep -q "Note.*query\|Note.*访问模式" "$f" 2>/dev/null; then
        if ! grep -q "indexes\|Index" "$f" 2>/dev/null; then
            report "R-IDX" "$f: 声明了访问模式但未定义 indexes（S0→索引推导要求）"
        fi
    fi

    # R-ENUM: status 字段应声明为 enum（而非 varchar）
    RENUM_OUT=$(grep -E 'status.*varchar' "$f" 2>/dev/null | while IFS= read -r line; do
        # 注意：${line} 必须花括号定界——bash 3.2 + UTF-8 下 $line 紧贴全角字符
        # 会被误并入变量名（set -u 报 unbound variable）
        echo "R-ENUM|${f}: status 字段用 varchar 而非 enum（${line}）"
    done)
    report_lines "$RENUM_OUT"
done

if [ "$VIOLATIONS" -eq 0 ]; then
    echo -e "${GREEN}✓ DBML IR lint 通过${NC}"
    exit 0
else
    echo ""
    echo "共 $VIOLATIONS 处违规（DBML IR lint）"
    [ "$VIOLATIONS" -gt 255 ] && VIOLATIONS=255
    exit "$VIOLATIONS"
fi
