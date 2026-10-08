#!/usr/bin/env python3
"""插件只能引用、只在项目内生效：所有 AI 工具经符号链接或原地加载使用 .agents/plugins，禁止复制；
项目插件挂在项目级目录（.claude/、.codex/、.grok/），不挂到所有项目共用的用户级目录。
启用哪些插件、钉在哪个 commit，只认仓库根 plugins-lock.json（维护命令：scripts/agents_plugins.py）。

用法：
  python3 tools/check/plugin_refs.py            # 仓库内：锁文件 + 适配器链接字面值（CI 无正文也能跑）
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agents_plugins import (  # noqa: E402
    CODEX_AGENTS_DIR, HOST_LINKS, HUB_DIR, LOCK_NAME, codex_agent_owner, expected_host_links,
    lock_problems, parse_lock,
)

HUB = ROOT / HUB_DIR
HOME = Path.home()


def repo_checks(root: Path = ROOT) -> tuple[list[str], list[str]]:
    """返回 (锁内插件名, 违规)。只比对仓库内容与链接字面值，不碰 ~/.zcode。"""
    try:
        data = json.loads((root / LOCK_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [], [f"PL-0 {LOCK_NAME} 缺失或不是合法 JSON：{exc}"]
    problems = lock_problems(data)
    if problems:
        return [], [f"PL-0 {LOCK_NAME}：{p}" for p in problems]
    plugins = parse_lock(data)
    host_links = expected_host_links(plugins)
    bad = []
    hub = root / HUB_DIR
    for entry in sorted(hub.iterdir()) if hub.is_dir() else []:
        if entry.name == "README.md" and entry.is_file() and not entry.is_symlink():
            continue
        if not entry.is_symlink():
            bad.append(f"PL-1 {HUB_DIR}/{entry.name} 不是符号链接（中枢只放指针，正文在 ~/.zcode/local-plugins）")
        elif entry.name not in plugins:
            bad.append(f"PL-1 {HUB_DIR}/{entry.name} 不在 {LOCK_NAME} 内（跑 scripts/agents_plugins.py sync 清理）")
    for d, _ in HOST_LINKS.values():
        base = root / d
        for entry in sorted(base.iterdir()) if base.is_dir() else []:
            rel = f"{d}/{entry.name}"
            if not entry.is_symlink():
                bad.append(f"PL-2 {rel} 是复制品/真实目录，应链到 {HUB_DIR}")
            elif rel not in host_links:
                bad.append(f"PL-2 {rel} 不在 {LOCK_NAME} 内或该插件未启用此宿主")
            elif os.readlink(entry) != host_links[rel]:
                bad.append(f"PL-2 {rel} 应指向 {host_links[rel]}")
        # 宿主目录存在（本仓库已接入该工具）时，锁内插件的适配器必须齐全；.codex/skills 已入库，CI 可验
        for rel in sorted(k for k in host_links if k.startswith(d + "/")):
            if base.is_dir() and not (root / rel).is_symlink():
                bad.append(f"PL-6 缺少 {rel}（跑 scripts/agents_plugins.py sync）")
    settings = root / ".claude" / "settings.json"
    if settings.is_file():
        claude = {p.name for p in plugins.values() if "claude" in p.hosts}
        markets = json.loads(settings.read_text(encoding="utf-8")).get("extraKnownMarketplaces", {})
        for key, spec in markets.items():
            src = spec.get("source", {})
            path = str(src.get("path", ""))
            if src.get("source") != "directory" or not path.startswith(f"./{HUB_DIR}/"):
                bad.append(f"PL-3 .claude/settings.json 插件源 {key} 必须是 directory + ./{HUB_DIR}/<name>（原地加载）")
            elif path.rsplit("/", 1)[-1] not in claude:
                bad.append(f"PL-3 .claude/settings.json 插件源 {key} 不在 {LOCK_NAME} 的 claude 宿主内")
    codex = {p.name for p in plugins.values() if "codex" in p.hosts}
    agents = root / CODEX_AGENTS_DIR
    for entry in sorted(agents.iterdir()) if agents.is_dir() else []:
        if not entry.is_symlink():
            bad.append(f"PL-4 {CODEX_AGENTS_DIR}/{entry.name} 是复制品，应经 {HUB_DIR} 链接（sdlc-workflow 用 link-codex.py）")
        elif codex_agent_owner(os.readlink(entry)) not in codex:
            bad.append(f"PL-4 {CODEX_AGENTS_DIR}/{entry.name} 所属插件不在 {LOCK_NAME} 的 codex 宿主内")
    cap = root / "capability-library" / "plugins"
    if cap.exists() and not cap.is_symlink():
        bad.append("PL-5 capability-library/plugins 不是符号链接（应整目录链到 ../.agents/plugins）")
    return sorted(plugins), bad


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
    names, bad = repo_checks()
    bad += local_checks(names) if args.local else []
    scope = "仓库 + 本机" if args.local else "仓库"
    if bad:
        print("\n".join(f"❌ {b}" for b in bad))
    else:
        print(f"✓ PL: 插件只以引用方式使用（{scope}，{LOCK_NAME} 锁定 {len(names)} 个：{', '.join(names)}）")
    return min(len(bad), 255)


if __name__ == "__main__":
    sys.exit(main())
