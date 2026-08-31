#!/usr/bin/env bash
# Codex 适配器（拼接型 fallback）：Codex 是否有独立 skill 目录机制尚未确认，
# 先按"只吃单一规则文件"处理：把 manifests/codex.yaml 里启用的 skill 的
# SKILL.md 正文（去掉 YAML frontmatter）拼接成一份生成文件。
#
# 输出路径待确认，暂定 ~/.codex/skills-library.md，此文件是生成物，
# 不要手动改，源头永远是 skills-library/skills/*/SKILL.md。
#
# 用法: adapters/codex.sh <skills-library-root>
set -euo pipefail

ROOT="${1:?usage: codex.sh <skills-library-root>}"
MANIFEST="$ROOT/manifests/codex.yaml"
OUT="$HOME/.codex/skills-library.md"

if [[ ! -f "$MANIFEST" ]]; then
  echo "no manifest: $MANIFEST, skip" >&2
  exit 0
fi

mkdir -p "$(dirname "$OUT")"

python3 - "$MANIFEST" "$ROOT" "$OUT" <<'PY'
import sys, os, re

manifest, root, out = sys.argv[1:4]
names = []
with open(manifest, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line.startswith("- "):
            names.append(line[2:].strip().strip('"').strip("'"))

def strip_frontmatter(text: str) -> str:
    m = re.match(r"^---\n.*?\n---\n", text, re.DOTALL)
    return text[m.end():] if m else text

sections = [
    "<!-- 本文件由 skills-library/adapters/codex.sh 自动生成，请勿手动编辑。 -->",
    "<!-- 源头: skills-library/skills/<name>/SKILL.md，改动请回到源头再跑 sync.sh -->",
    "",
]
missing = []
for name in names:
    path = os.path.join(root, "skills", name, "SKILL.md")
    if not os.path.isfile(path):
        missing.append(name)
        continue
    with open(path, encoding="utf-8") as f:
        body = strip_frontmatter(f.read()).strip()
    sections.append(f"## Skill: {name}\n\n{body}\n")

with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(sections))

print(f"generated: {out} ({len(names) - len(missing)} skills)")
for m in missing:
    print(f"WARN: skill dir missing, skip: {m}", file=sys.stderr)
PY
