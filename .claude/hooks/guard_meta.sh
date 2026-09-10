#!/usr/bin/env bash
# PreToolUse hook (Write|Edit): 拦截对 .claude 元文件的修改，要求用户确认
# 失败兜底：任何异常 exit 0（fail-open，不让 hook bug 锁死写操作）
#
# 运行时依赖：bash >= 3.2, grep, sed, jq（可选，缺失时 fallback 到 grep）

# --- bash 版本检查（最低 3.2）---
if [ -z "$BASH_VERSION" ]; then
    echo "[hook:guard_meta] 错误：此脚本必须在 bash 下运行，当前 shell 为 $(ps -p $$ -o comm= 2>/dev/null || echo 'unknown')。" >&2
    echo "[hook:guard_meta] 请使用 'bash .claude/hooks/guard_meta.sh' 执行。" >&2
    exit 1
fi
_BASH_MAJOR="${BASH_VERSINFO[0]:-0}"
_BASH_MINOR="${BASH_VERSINFO[1]:-0}"
if (( _BASH_MAJOR < 3 )) || { (( _BASH_MAJOR == 3 )) && (( _BASH_MINOR < 2 )); }; then
    echo "[hook:guard_meta] 错误：需要 bash >= 3.2，当前版本为 ${BASH_VERSION}。" >&2
    echo "[hook:guard_meta] 请通过 'brew install bash' 升级 bash。" >&2
    exit 1
fi
unset _BASH_MAJOR _BASH_MINOR

set +e
trap 'exit 0' ERR

# 读 stdin JSON
INPUT=$(cat 2>/dev/null)
if [ -z "$INPUT" ]; then
    exit 0
fi

# 提取 tool_input.file_path（不依赖 jq，先尝试 jq，失败 fallback 到 grep）
FILE_PATH=""
if command -v jq >/dev/null 2>&1; then
    FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""' 2>/dev/null)
fi
if [ -z "$FILE_PATH" ]; then
    FILE_PATH=$(echo "$INPUT" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
fi

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# JSON 安全转义 FILE_PATH（防止双引号/反斜杠等破坏输出 JSON）
if command -v jq >/dev/null 2>&1; then
    FILE_PATH_ESCAPED=$(printf '%s' "$FILE_PATH" | jq -Rs '. | rtrimstr("\n")' | sed 's/^"//;s/"$//')
else
    FILE_PATH_ESCAPED=$(printf '%s' "$FILE_PATH" | sed 's/\\/\\\\/g; s/"/\\"/g')
fi

# 拦截 regex：rules / skills / IDENTITY / SOUL / settings.json
# 注意：MEMORY.md 和 memory/* 不拦截（半自动进化允许 AI 写入，但走 git review）
# .agents/skills/ 是 skills 物理位置（.claude/skills 是 symlink 过去），同等保护
GUARD_REGEX='(\.claude/(rules/|skills/|IDENTITY\.md|SOUL\.md|settings\.json$)|\.agents/skills/)'

if echo "$FILE_PATH" | grep -qE "$GUARD_REGEX"; then
    # 输出 JSON 让用户确认
    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": "拦截：修改 \`${FILE_PATH_ESCAPED}\` 是项目契约级文件（rules / skills / IDENTITY / SOUL / settings.json），需要人类确认。如果确实要改，请明确告诉 Claude 'apply' 或直接编辑。"
  }
}
EOF
    exit 0
fi

# 默认放行
exit 0
