#!/usr/bin/env bash
# UserPromptSubmit hook: 注入项目身份头 + 最近 3 条 memory 索引到主对话 context
# 失败兜底：任何异常 exit 0，绝不阻塞用户
#
# 运行时依赖：bash >= 3.2, awk, grep, sed, head, ls

# --- bash 版本检查（最低 3.2）---
if [ -z "$BASH_VERSION" ]; then
    echo "[hook:inject_context] 错误：此脚本必须在 bash 下运行，当前 shell 为 $(ps -p $$ -o comm= 2>/dev/null || echo 'unknown')。" >&2
    echo "[hook:inject_context] 请使用 'bash .claude/hooks/inject_context.sh' 执行。" >&2
    exit 1
fi
_BASH_MAJOR="${BASH_VERSINFO[0]:-0}"
_BASH_MINOR="${BASH_VERSINFO[1]:-0}"
if (( _BASH_MAJOR < 3 )) || { (( _BASH_MAJOR == 3 )) && (( _BASH_MINOR < 2 )); }; then
    echo "[hook:inject_context] 错误：需要 bash >= 3.2，当前版本为 ${BASH_VERSION}。" >&2
    echo "[hook:inject_context] 请通过 'brew install bash' 升级 bash。" >&2
    exit 1
fi
unset _BASH_MAJOR _BASH_MINOR

set +e
trap 'exit 0' ERR

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
IDENTITY="$PROJECT_DIR/.claude/IDENTITY.md"
MEMORY_DIR="$PROJECT_DIR/.claude/memory"
MEMORY_INDEX="$PROJECT_DIR/.claude/MEMORY.md"

# 体积上限（避免污染 context window）
MAX_BYTES=1024

OUT=""

# 1) IDENTITY 头：取 Role + Mission 段（前 ~10 行非空内容）
if [ -f "$IDENTITY" ]; then
    HEAD=$(awk '/^## (Role|Mission)/{p=1} p && /^## /{c++; if(c>2) exit} p' "$IDENTITY" 2>/dev/null | head -c 600)
    if [ -n "$HEAD" ]; then
        OUT="<project-identity>
$HEAD
</project-identity>"
    fi
fi

# 2) 最近 3 条 memory 条目摘要（如果存在）
if [ -d "$MEMORY_DIR" ]; then
    RECENT=$(ls -t "$MEMORY_DIR"/*.md 2>/dev/null | grep -v README.md | head -3)
    if [ -n "$RECENT" ]; then
        SNIPPETS=""
        for f in $RECENT; do
            DESC=$(grep -m1 "^description:" "$f" 2>/dev/null | sed 's/^description: *//')
            NAME=$(basename "$f" .md)
            if [ -n "$DESC" ]; then
                SNIPPETS="${SNIPPETS}- ${NAME}: ${DESC}
"
            fi
        done
        if [ -n "$SNIPPETS" ]; then
            OUT="$OUT

<recent-memory>
$SNIPPETS</recent-memory>"
        fi
    fi
fi

# 3) 截断到 MAX_BYTES，输出到 stdout（被 Claude Code 注入为 additionalContext）
if [ -n "$OUT" ]; then
    echo "$OUT" | head -c "$MAX_BYTES"
fi

exit 0
