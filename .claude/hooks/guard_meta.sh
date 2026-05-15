#!/usr/bin/env bash
# PreToolUse hook (Write|Edit): 拦截对 .claude 元文件的修改，要求用户确认
# 失败兜底：任何异常 exit 0（fail-open，不让 hook bug 锁死写操作）

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

# 拦截 regex：rules / skills / IDENTITY / SOUL / settings.json
# 注意：MEMORY.md 和 memory/* 不拦截（半自动进化允许 AI 写入，但走 git review）
GUARD_REGEX='\.claude/(rules/|skills/|IDENTITY\.md|SOUL\.md|settings\.json$)'

if echo "$FILE_PATH" | grep -qE "$GUARD_REGEX"; then
    # 输出 JSON 让用户确认
    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": "拦截：修改 \`$FILE_PATH\` 是项目契约级文件（rules / skills / IDENTITY / SOUL / settings.json），需要人类确认。如果确实要改，请明确告诉 Claude 'apply' 或直接编辑。"
  }
}
EOF
    exit 0
fi

# 默认放行
exit 0
