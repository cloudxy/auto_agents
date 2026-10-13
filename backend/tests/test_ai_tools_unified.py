"""多 AI 工具共用同一份内容：AGENTS.md 是唯一指南，.agents/ 是 skill 与规则的唯一来源，各工具只放链接 / 配置。

防回退：有人把链接换成复制品、新建第二份指令文件、或让 Gemini 配置不再指向 AGENTS.md 时变红。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_claude_md_imports_agents_md_first():
    lines = (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "@AGENTS.md"


def test_gemini_reads_agents_md_from_root_and_subdirs():
    gemini_md = ROOT / "GEMINI.md"
    assert gemini_md.is_symlink() and os.readlink(gemini_md) == "AGENTS.md"
    names = json.loads((ROOT / ".gemini" / "settings.json").read_text(encoding="utf-8"))["context"]["fileName"]
    assert "AGENTS.md" in ([names] if isinstance(names, str) else names)


def test_claude_adapters_are_links_into_hub():
    for name in ("skills", "rules"):
        link = ROOT / ".claude" / name
        assert link.is_symlink() and os.readlink(link) == f"../.agents/{name}", name
        assert any((ROOT / ".agents" / name).iterdir()), name


def test_no_second_copy_of_instructions():
    """根目录只有 AGENTS.md 一份正文；其他工具的指令文件只能是导入或链接。"""
    copies = [p.name for p in ROOT.glob("*.md") if p.name.upper() in {"GEMINI.MD", "CODEX.MD", "GROK.MD", "WARP.MD"}
              and not p.is_symlink()]
    assert copies == []
    assert not (ROOT / ".claude" / "CLAUDE.md").exists()
