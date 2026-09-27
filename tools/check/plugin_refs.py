#!/usr/bin/env python3
"""插件只能引用、只在项目内生效：所有 AI 工具经符号链接或原地加载使用 .agents/plugins，禁止复制；
项目插件挂在项目级目录（.claude/、.codex/、.grok/），不挂到所有项目共用的用户级目录。

用法：
  python3 tools/check/plugin_refs.py            # 仓库内适配器（CI 可跑）
  python3 tools/check/plugin_refs.py --local    # 另查本机各工具的缓存与用户级链接

退出码 = 违规数（上限 255）。规则来源：.agents/README.md「只能引用」。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / ".agents" / "plugins"
HOME = Path.home()


def hub_names() -> list[str]:
    return sorted(p.name for p in HUB.iterdir() if p.name != "README.md") if HUB.is_dir() else []


def lexical_target(link: Path) -> str:
    """Where a link points, without touching the filesystem: hub links dangle in CI (no ~/.zcode)."""
    return os.path.normpath(os.path.join(link.parent, os.readlink(link)))


def same(a: Path, b: Path) -> bool:
    try:
        return a.resolve(strict=True) == b.resolve(strict=True)
    except OSError:
        return False


def repo_checks(names: list[str]) -> list[str]:
    bad = []
    for name in names:
        entry = HUB / name
        if not entry.is_symlink():
            bad.append(f"PL-1 .agents/plugins/{name} 不是符号链接（中枢只放指针，正文在 ~/.zcode/local-plugins）")
    for host in (".claude/plugins", ".grok/plugins"):
        d = ROOT / host
        for entry in sorted(d.iterdir()) if d.is_dir() else []:
            if not entry.is_symlink():
                bad.append(f"PL-2 {host}/{entry.name} 是真实文件/目录，应链到 .agents/plugins/{entry.name}")
            elif lexical_target(entry) != str(HUB / entry.name):
                bad.append(f"PL-2 {host}/{entry.name} 没有指向 .agents/plugins/{entry.name}")
    settings = ROOT / ".claude" / "settings.json"
    if settings.is_file():
        markets = json.loads(settings.read_text(encoding="utf-8")).get("extraKnownMarketplaces", {})
        for key, spec in markets.items():
            src = spec.get("source", {})
            path = str(src.get("path", ""))
            if src.get("source") != "directory" or not path.startswith("./.agents/plugins/"):
                bad.append(f"PL-3 .claude/settings.json 插件源 {key} 必须是 directory + ./.agents/plugins/<name>（原地加载）")
    for sub in ("skills", "agents"):
        d = ROOT / ".codex" / sub
        for entry in sorted(d.iterdir()) if d.is_dir() else []:
            if not entry.is_symlink():
                bad.append(f"PL-4 .codex/{sub}/{entry.name} 是复制品，应链到 .agents/plugins（sdlc-workflow 用 link-codex.py）")
            elif not lexical_target(entry).startswith(str(HUB) + os.sep):
                bad.append(f"PL-4 .codex/{sub}/{entry.name} 没有经 .agents/plugins 引用")
    cap = ROOT / "capability-library" / "plugins"
    if cap.exists() and not cap.is_symlink():
        bad.append("PL-5 capability-library/plugins 不是符号链接（应整目录链到 ../.agents/plugins）")
    return bad


def local_checks(names: list[str]) -> list[str]:
    bad = []
    for name in names:
        link = HOME / ".codex" / "skills" / name
        if link.is_symlink() or link.exists():
            bad.append(f"PL-L1 ~/.codex/skills/{name} 挂在用户级，会进入所有项目；改挂 .codex/skills/{name}")
        for cache in (HOME / ".codex/plugins/cache", HOME / ".claude/plugins/cache", HOME / ".zcode/cli/plugins/cache"):
            for copy in sorted(cache.glob(f"*/{name}")) if cache.is_dir() else []:
                if copy.is_dir() and not copy.is_symlink():
                    bad.append(f"PL-L2 复制安装：{copy}（改用引用方式，卸载该副本）")
        grok_user = HOME / ".grok" / "plugins" / name
        if grok_user.exists() and not grok_user.is_symlink():
            bad.append(f"PL-L3 ~/.grok/plugins/{name} 是复制品")
    registry = HOME / ".grok" / "installed-plugins" / "registry.json"
    if registry.is_file():
        text = registry.read_text(encoding="utf-8")
        for name in names:
            if f'"{name}"' in text:
                bad.append(f"PL-L3 grok plugin install 留下了 {name} 的副本（~/.grok/installed-plugins）")
    for toml in sorted((HOME / ".codex" / "agents").glob("sdlc-workflow-*.toml")):
        bad.append(f"PL-L4 {toml} 挂在用户级，会进入所有项目；改用 link-codex.py --project")
    for d in (ROOT / ".claude/plugins", ROOT / ".grok/plugins", ROOT / ".codex/skills", ROOT / ".codex/agents"):
        for entry in sorted(d.iterdir()) if d.is_dir() else []:
            if entry.is_symlink() and not entry.exists():
                bad.append(f"PL-L5 {entry.relative_to(ROOT)} 是悬空链接（源头 ~/.zcode/local-plugins 缺失？）")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--local", action="store_true", help="also check tool caches, user-level leaks and dangling links")
    args = ap.parse_args()
    names = hub_names()
    bad = repo_checks(names) + (local_checks(names) if args.local else [])
    scope = "仓库 + 本机" if args.local else "仓库"
    if bad:
        print("\n".join(f"❌ {b}" for b in bad))
    else:
        print(f"✓ PL: 插件只以引用方式使用（{scope}，{len(names)} 个中枢插件）")
    return min(len(bad), 255)


if __name__ == "__main__":
    sys.exit(main())
