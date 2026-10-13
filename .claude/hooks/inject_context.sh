#!/usr/bin/env bash
# UserPromptSubmit hook: 注入项目身份头 + 最近 3 条 memory 索引到主对话 context
# 失败兜底：任何异常 exit 0，绝不阻塞用户
#
# 运行时依赖：bash >= 3.2, awk, grep, sed, head, ls；iconv 可选（UTF-8 安全截断）

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

# 体积预算（避免污染 context window）：身份段与记忆段分开计，闭合标签不参与截断。
# 曾经整体一刀切 1024 字节：身份段一长就把记忆段挤掉，连 </recent-memory> 都被截断。
IDENT_MAX=1200       # 身份头（Role + Mission，当前约 1.05 KB，留余量免得截在半句）
MEMORY_LINE_MAX=240  # 单条记忆摘要
MEMORY_MAX=600       # 记忆段合计（最多 3 条，放不下的整条丢弃，不截半条）

# 按字节截断后丢掉被截断的半个 UTF-8 字符（head -c 会把中文切成非法字节序列）；
# 没有 iconv 时退化为纯字节截断。iconv -c 丢弃字节时退出码为 1，必须吞掉：
# 本脚本 trap 'exit 0' ERR，非零退出会让整个 hook 静默不输出
utf8_head() {
    if command -v iconv >/dev/null 2>&1; then
        head -c "$1" | iconv -c -f UTF-8 -t UTF-8 2>/dev/null || true
    else
        head -c "$1"
    fi
}

OUT=""

# 1) IDENTITY 头：取 Role + Mission 段（前 ~10 行非空内容）
if [ -f "$IDENTITY" ]; then
    HEAD=$(awk '/^## (Role|Mission)/{p=1} p && /^## /{c++; if(c>2) exit} p' "$IDENTITY" 2>/dev/null | utf8_head "$IDENT_MAX")
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
        USED=0
        for f in $RECENT; do
            DESC=$(grep -m1 "^description:" "$f" 2>/dev/null | sed 's/^description: *//')
            NAME=$(basename "$f" .md)
            if [ -n "$DESC" ]; then
                LINE=$(printf '%s' "- ${NAME}: ${DESC}" | utf8_head "$MEMORY_LINE_MAX")
                LEN=$(printf '%s\n' "$LINE" | wc -c | tr -d ' ')
                if [ $((USED + LEN)) -gt "$MEMORY_MAX" ]; then
                    break
                fi
                SNIPPETS="${SNIPPETS}${LINE}
"
                USED=$((USED + LEN))
            fi
        done
        if [ -n "$SNIPPETS" ]; then
            OUT="$OUT

<recent-memory>
$SNIPPETS</recent-memory>"
        fi
    fi
fi

# 3) 输出到 stdout（被 Claude Code 注入为 additionalContext）；各段已按预算截好，
#    合计 ≤ IDENT_MAX + MEMORY_MAX + 标签，约 1.9 KB
if [ -n "$OUT" ]; then
    echo "$OUT"
fi

exit 0
