#!/usr/bin/env bash
# Claude Code 适配器：为 manifests/claude-code.yaml 里启用的每个 skill 建 symlink 到
# ~/.claude/skills/<name>，Claude Code 原生按目录识别 SKILL.md。
#
# 用法: adapters/claude-code.sh <capability-library-root>
set -euo pipefail

ROOT="${1:?usage: claude-code.sh <capability-library-root>}"
MANIFEST="$ROOT/manifests/claude-code.yaml"
TARGET_DIR="$HOME/.claude/skills"

if [[ ! -f "$MANIFEST" ]]; then
  echo "no manifest: $MANIFEST, skip" >&2
  exit 0
fi

mkdir -p "$TARGET_DIR"

# manifest 格式：每行一个 skill 名（YAML list），如：
# - dataviz
# - pdf-extractor
python3 - "$MANIFEST" "$ROOT" "$TARGET_DIR" <<'PY'
import sys, os
manifest, root, target_dir = sys.argv[1:4]
names = []
with open(manifest, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line.startswith("- "):
            names.append(line[2:].strip().strip('"').strip("'"))

kept = set()
for name in names:
    src = os.path.join(root, "skills", name)
    dst = os.path.join(target_dir, name)
    if not os.path.isdir(src):
        print(f"WARN: skill dir missing, skip: {src}", file=sys.stderr)
        continue
    if os.path.islink(dst) or os.path.exists(dst):
        if os.path.islink(dst) and os.path.realpath(dst) == os.path.realpath(src):
            kept.add(name)
            continue
        os.remove(dst) if os.path.islink(dst) else None
    os.symlink(src, dst)
    kept.add(name)
    print(f"linked: {name}")

# 清理 manifest 里已移除的 skill 对应的旧 symlink（只清理本脚本管理的 symlink，不动其他文件）
for existing in os.listdir(target_dir):
    p = os.path.join(target_dir, existing)
    if os.path.islink(p) and existing not in kept:
        real = os.path.realpath(p)
        if real.startswith(os.path.join(root, "skills")):
            os.remove(p)
            print(f"unlinked (removed from manifest): {existing}")
PY
