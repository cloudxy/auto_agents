#!/usr/bin/env bash
# ============================================================================
# check-db-ir.sh — DBML IR 静态 lint（D 线 D2，ADR-0002 执法面）
# 规则来源：atlas lint 规则清单 + schemalint + sqlcheck 语义精选
# 退出码 = 违规数；无 *.dbml 文件时静默通过（不阻塞非 DB 改动）
# ============================================================================

set -u

VIOLATIONS=0
RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'

report() {
    local rule="$1" detail="$2"
    echo -e "${RED}✗ [${rule}]${NC} ${detail}"
    VIOLATIONS=$((VIOLATIONS + 1))
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

echo "DBML IR 静态 lint（${#DBML_FILES[@]} 个文件）"
echo "=================================="

for f in $DBML_FILES; do
    # R-NAM: 表名 snake_case 复数
    grep -E 'Table [a-z]+[^s{]' "$f" 2>/dev/null | while IFS= read -r line; do
        table_name=$(echo "$line" | sed 's/Table \([a-z_]*\).*/\1/')
        if ! echo "$table_name" | grep -qE '^[a-z]+(_[a-z]+)*s$'; then
            report "R-NAM" "$f: 表名 '$table_name' 应为 snake_case 复数（如 spider_tasks）"
        fi
    done

    # R-AUD: 审计字段（created_at + updated_at 必备）
    python3 -c "
import sys, re
content = open('$f').read()
tables = re.findall(r'Table\s+(\w+)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', content, re.DOTALL)
for name, body in tables:
    if 'created_at' not in body:
        print(f'R-AUD|$f: 表 {name} 缺 created_at 审计字段')
    if 'updated_at' not in body:
        print(f'R-AUD|$f: 表 {name} 缺 updated_at 审计字段')
" 2>/dev/null | while IFS='|' read -r rule detail; do
        report "$rule" "$detail"
    done

    # R-FK: Ref 声明引用完整性
    grep -c "Ref:" "$f" >/dev/null 2>&1 || report "R-FK" "$f: 零 Ref 声明（单表设计或缺失关系？）"

    # R-IDX: 有查询模式声明的表应有索引注释
    if grep -q "Note.*query\|Note.*访问模式" "$f" 2>/dev/null; then
        if ! grep -q "indexes\|Index" "$f" 2>/dev/null; then
            report "R-IDX" "$f: 声明了访问模式但未定义 indexes（S0→索引推导要求）"
        fi
    fi

    # R-ENUM: status 字段应声明为 enum（而非 varchar）
    grep -E 'status.*varchar' "$f" 2>/dev/null | while IFS= read -r line; do
        report "R-ENUM" "$f: status 字段用 varchar 而非 enum（$line）"
    done
done

if [ $VIOLATIONS -eq 0 ]; then
    echo -e "${GREEN}✓ DBML IR lint 通过${NC}"
fi
exit $VIOLATIONS
