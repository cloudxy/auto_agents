#!/usr/bin/env bash
# Stop hook: 检测会话是否触及"踩坑/约定"信号，提示用户归档为 memory
# 失败兜底：任何异常 exit 0；绝不阻塞 stop

set +e
trap 'exit 0' ERR

# 读 stdin JSON
INPUT=$(cat 2>/dev/null)
if [ -z "$INPUT" ]; then
    exit 0
fi

# 提取 transcript_path
TRANSCRIPT=""
if command -v jq >/dev/null 2>&1; then
    TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // ""' 2>/dev/null)
fi
if [ -z "$TRANSCRIPT" ]; then
    TRANSCRIPT=$(echo "$INPUT" | grep -oE '"transcript_path"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed 's/.*"transcript_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
fi

if [ -z "$TRANSCRIPT" ] || [ ! -f "$TRANSCRIPT" ]; then
    exit 0
fi

# 关键词命中判定：踩坑 / 约定 / 下次记住 等信号
# 用 grep -c 数命中行数（不读全文，只 tail 最近 200 行避免大 transcript 卡住）
KEYWORDS='坑|pitfall|gotcha|记住|下次|约定|不要再|总是会|经验|教训|TIL'
HIT_COUNT=$(tail -n 200 "$TRANSCRIPT" 2>/dev/null | grep -cE "$KEYWORDS" 2>/dev/null)
HIT_COUNT=${HIT_COUNT:-0}
# 防 grep -c 在多文件模式下输出多行
HIT_COUNT=$(echo "$HIT_COUNT" | head -1)

# 至少命中 2 次才提示，避免噪音
if [ "$HIT_COUNT" -ge 2 ] 2>/dev/null; then
    # Stop hook 用 stderr 输出建议（用户可见），不阻塞
    cat >&2 <<EOF

[memory-curator hint] 本次会话有 $HIT_COUNT 处可能值得归档的信号（踩坑/约定/经验）。
如要整理为项目记忆，请说："拉起 memory-curator 整理本次会话"。
（当前 .claude/memory/ 是项目级记忆，与个人 ~/.claude memory 区分）
EOF
fi

exit 0
