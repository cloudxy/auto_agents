#!/usr/bin/env bash
# ============================================================================
# check-db-migrations.sh — Alembic 迁移破坏性变更检测（D 线 D2，ADR-0002 执法面）
# 规则语义来源：ankane/strong_migrations 检查项清单
# 退出码 = 违规数
# ============================================================================

set -u

VERSIONS_DIR="backend/alembic/versions"
VIOLATIONS=0
RED='\033[0;31m'; GREEN='\033[0'; NC='\033[0m'

report() {
    local rule="$1" detail="$2"
    echo -e "${RED}✗ [${rule}]${NC} ${detail}"
    VIOLATIONS=$((VIOLATIONS + 1))
}

if [ ! -d "$VERSIONS_DIR" ]; then
    echo "check-db-migrations: 迁移目录不存在，跳过"
    exit 0
fi

echo "迁移破坏性变更检测（strong_migrations 语义）"
echo "=============================================="

# 获取新增/修改的迁移文件（git diff 或全部）
if git rev-parse --git-dir > /dev/null 2>&1; then
    CHANGED=$(git diff --name-only --cached HEAD 2>/dev/null | grep "^${VERSIONS_DIR}/.*\.py$" || true)
    if [ -z "$CHANGED" ]; then
        CHANGED=$(git diff --name-only HEAD 2>/dev/null | grep "^${VERSIONS_DIR}/.*\.py$" || true)
    fi
fi
if [ -z "$CHANGED" ]; then
    # 无增量 → 扫全部（CI 模式兜底）
    CHANGED=$(find "$VERSIONS_DIR" -name "*.py" -not -name "__init__.py" 2>/dev/null)
fi

for f in $CHANGED; do
    [ -f "$f" ] || continue

    # SM-1: drop_table 需 expand-contract 标注
    if grep -q "drop_table\|op.drop" "$f" 2>/dev/null; then
        if ! grep -qE "expand.contract|收缩阶段|contract phase" "$f" 2>/dev/null; then
            report "SM-1" "$f: drop_table 无 expand-contract 标注（破坏性变更须分步）"
        fi
    fi

    # SM-2: drop_column 同上
    if grep -q "drop_column" "$f" 2>/dev/null; then
        if ! grep -qE "expand.contract|收缩阶段|contract phase" "$f" 2>/dev/null; then
            report "SM-2" "$f: drop_column 无 expand-contract 标注"
        fi
    fi

    # SM-3: 类型收窄（varchar → int / text → varchar）
    if grep -qE "alter_column.*String.*Integer|alter_column.*Text.*String" "$f" 2>/dev/null; then
        report "SM-3" "$f: 检测到类型收窄 alter（需 expand-contract 双步 + 数据迁移确认）"
    fi

    # SM-4: rename 未走 add+drop 双步
    if grep -qE "rename_table|rename_column" "$f" 2>/dev/null; then
        if ! grep -qE "expand.contract|双步|rename.*add.*drop" "$f" 2>/dev/null; then
            report "SM-4" "$f: rename_table/column 未走 add+drop 双步（数据丢失风险）"
        fi
    fi

    # SM-5: NOT NULL 加列无 default（python 精确检测：同一 add_column 调用块内 nullable=False 且无 server_default）
    python3 -c "
import ast, sys
source = open('$f').read()
if 'SM-EXEMPT' in source:
    sys.exit(0)
try:
    tree = ast.parse(source)
except SyntaxError:
    sys.exit(0)
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and getattr(node.func, 'attr', '') == 'add_column':
        has_not_null = False
        has_default = False
        for kw in node.keywords:
            if kw.arg == 'nullable' and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                has_not_null = True
            if kw.arg == 'server_default':
                has_default = True
        if has_not_null and not has_default:
            print('SM-5|$f: add_column + NOT NULL 但无 server_default（存量行会炸）')
            sys.exit(0)
" 2>/dev/null | while IFS='|' read -r rule detail; do
        report "$rule" "$detail"
    done

    # SM-6: 大表 ALTER 锁表风险标注
    BIG_TABLES="spider_results|operation_logs|skill_reviews"
    if grep -qE "alter_table.*(${BIG_TABLES})|alter_column.*(${BIG_TABLES})" "$f" 2>/dev/null; then
        if ! grep -qE "gh-ost|pt-osc|online DDL|锁表" "$f" 2>/dev/null; then
            report "SM-6" "$f: 大表 ALTER 未标注 gh-ost/pt-osc（锁表风险）"
        fi
    fi

    # SM-7: downgrade 缺失或空
    if grep -A 3 "def downgrade" "$f" 2>/dev/null | grep -q "pass$" ; then
        report "SM-7" "$f: downgrade 为 pass（必须可回滚——审计 10.2-G）"
    fi

    # SM-8: autogenerate 产出的迁移含 AI 手写 SQL（不该出现在 migrate() 里的 raw SQL）
    if grep -E "op\.execute.*sa\.text" "$f" 2>/dev/null | grep -v "INSERT INTO capability\|UPDATE.*SET\|SELECT 1"; then
        if ! grep -qE "# 回填|backfill|migration data" "$f" 2>/dev/null; then
            report "SM-8" "$f: op.execute 含裸 SQL 但未标注为数据回填（LLM 禁写迁移 SQL——ADR-0002）"
        fi
    fi
done

if [ $VIOLATIONS -eq 0 ]; then
    echo -e "${GREEN}✓ 迁移破坏性变更检测通过${NC}"
fi
exit $VIOLATIONS
