#!/usr/bin/env bash
# ============================================================================
# check-db-migrations.sh — Alembic 迁移破坏性变更检测（D 线 D2，ADR-0002 执法面）
# 规则语义来源：ankane/strong_migrations 检查项清单
# 退出码 = 违规数（超过 255 截断为 255，避免 256 取模归零再次假绿）
#
# 2026-09 T2 修复（三类缺陷）：
# 1. 管道子 shell 丢计数：原 `python3 ... | while read; do report; done` 中
#    report() 的 VIOLATIONS 自增发生在管道子 shell，无法传回主 shell，
#    导致 SM-1/SM-5 有违规仍 exit 0 假绿。现改为「命令替换捕获检测输出 +
#    report_lines 以 heredoc 喂 while」——heredoc 不产生子 shell，
#    且全程 bash 3.2 兼容（不依赖进程替换）。
# 2. SM-5 检测语义缺陷：原实现只检查 add_column 调用自身的 keywords，
#    而真实 Alembic 写法 nullable=False 在 sa.Column(...) 实参里，
#    导致该规则对真实迁移永远不触发。现同时扫描 add_column 的 sa.Column 实参。
# 3. SM-8 判断的第二个 grep 缺 -q，命中行泄入 stdout 污染门禁日志。
# ============================================================================
# 检测输出协议：检测器逐行打印 `规则ID|明细`，由 report_lines 在主 shell 计数。
# 豁免：迁移文件内含 SM-EXEMPT 注释即整体跳过（须注明豁免理由）。

set -u

VERSIONS_DIR="backend/alembic/versions"
VIOLATIONS=0
CHANGED=""
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

    # SM-1/2: upgrade() 内 drop_table/drop_column 需 expand-contract 标注
    # （downgrade() 内的 drop 是合法回滚，不检查）
    SM1_OUT=$(python3 -c '
import ast, sys
path = sys.argv[1]
try:
    source = open(path).read()
except OSError:
    sys.exit(0)
if "SM-EXEMPT" in source:
    sys.exit(0)
try:
    tree = ast.parse(source)
except SyntaxError:
    sys.exit(0)
upgrade_fn = None
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "upgrade":
        upgrade_fn = node
        break
if upgrade_fn is None:
    sys.exit(0)
for node in ast.walk(upgrade_fn):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr in ("drop_table", "drop_column"):
            print(f"SM-1|{path}: upgrade() 第 {node.lineno} 行 {node.func.attr} 无 expand-contract 标注（破坏性变更须分步）")
' "$f" 2>/dev/null || true)
    report_lines "$SM1_OUT"

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

    # SM-5: NOT NULL 加列无 default（AST 精确检测，兼容两种写法：
    # op.add_column(t, sa.Column(..., nullable=False)) 与 op.add_column(..., nullable=False)）
    SM5_OUT=$(python3 -c '
import ast, sys
path = sys.argv[1]
try:
    source = open(path).read()
except OSError:
    sys.exit(0)
if "SM-EXEMPT" in source:
    sys.exit(0)
try:
    tree = ast.parse(source)
except SyntaxError:
    sys.exit(0)
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_column":
        column_calls = [a for a in node.args if isinstance(a, ast.Call)
                        and getattr(a.func, "attr", "") == "Column"]
        has_not_null = False
        has_default = False
        for call in [node] + column_calls:
            for kw in call.keywords:
                if kw.arg == "nullable" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                    has_not_null = True
                if kw.arg == "server_default":
                    has_default = True
        if has_not_null and not has_default:
            print(f"SM-5|{path}: 第 {node.lineno} 行 add_column + NOT NULL 但无 server_default（存量行会炸）")
' "$f" 2>/dev/null || true)
    report_lines "$SM5_OUT"

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
    if grep -E "op\.execute.*sa\.text" "$f" 2>/dev/null | grep -qv "INSERT INTO capability\|UPDATE.*SET\|SELECT 1"; then
        if ! grep -qE "# 回填|backfill|migration data" "$f" 2>/dev/null; then
            report "SM-8" "$f: op.execute 含裸 SQL 但未标注为数据回填（LLM 禁写迁移 SQL——ADR-0002）"
        fi
    fi
done

if [ "$VIOLATIONS" -eq 0 ]; then
    echo -e "${GREEN}✓ 迁移破坏性变更检测通过${NC}"
    exit 0
else
    echo ""
    echo "共 $VIOLATIONS 处违规，请按 expand-contract 分步改造（豁免须注明 SM-EXEMPT + 理由）"
    [ "$VIOLATIONS" -gt 255 ] && VIOLATIONS=255
    exit "$VIOLATIONS"
fi
