#!/usr/bin/env python3
"""外部插件：引用 + 锁文件（仓库根 plugins-lock.json）。

插件正文不进仓库，只在本机 localPath（如 ~/.zcode/local-plugins/<name>）维护；仓库只提交锁文件
（git 来源 + 固定 commit）和各工具适配器里的相对符号链接。所有 AI 工具只能引用，禁止复制。

用法：
  python3 scripts/agents_plugins.py sync           # 本机缺正文就按锁克隆；建好链接；删掉锁外插件的链接
  python3 scripts/agents_plugins.py check          # 只读：正文、来源、commit、链接是否与锁一致
  python3 scripts/agents_plugins.py check --strict # commit 漂移也算违规
  python3 scripts/agents_plugins.py lock [name…]   # 把锁里的 commit 更新为本机正文 HEAD（须已推到远端）

已存在的正文由维护者（如 ~/.zcode/plugin-updater）管理，本脚本只读不改；只在正文缺失时克隆。
仓库侧（CI 无正文也能跑）的校验在 tools/check/plugin_refs.py（arch.sh PL 段）。
退出码 = 违规数（上限 255）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_NAME = "plugins-lock.json"
HUB_DIR = ".agents/plugins"
# 宿主 → (适配器目录, 链到插件里的子路径)；适配器条目 <dir>/<name> → ../../.agents/plugins/<name>[/<sub>]
HOST_LINKS = {
    "claude": (".claude/plugins", ""),
    "grok": (".grok/plugins", ""),
    "codex": (".codex/skills", "skills"),
}
CODEX_AGENTS_DIR = ".codex/agents"
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Plugin:
    name: str
    source: str
    ref: str
    commit: str
    local_path: str
    hosts: tuple[str, ...]

    def body(self, home: Path) -> Path:
        """本机正文目录（localPath 以 ~/ 开头，按给定家目录展开）。"""
        return home / self.local_path[2:]


def lock_problems(data: object) -> list[str]:
    """锁文件结构校验；返回问题列表（空 = 合法）。"""
    if not isinstance(data, dict) or data.get("version") != 1:
        return ["version 必须为 1"]
    plugins = data.get("plugins")
    if not isinstance(plugins, dict):
        return ["plugins 必须是对象"]
    bad = []
    for name, spec in plugins.items():
        if not _NAME.match(name):
            bad.append(f"{name}: 插件名只能是小写字母、数字和连字符")
        if not isinstance(spec, dict):
            bad.append(f"{name}: 条目必须是对象")
            continue
        if not str(spec.get("source", "")).startswith("https://"):
            bad.append(f"{name}: source 必须是 https git 地址")
        if not spec.get("ref"):
            bad.append(f"{name}: ref 不能为空")
        if not _SHA.match(str(spec.get("commit", ""))):
            bad.append(f"{name}: commit 必须是 40 位小写十六进制")
        if not str(spec.get("localPath", "")).startswith("~/"):
            bad.append(f"{name}: localPath 必须在家目录下（~/…），正文不进仓库")
        hosts = spec.get("hosts", [])
        if not isinstance(hosts, list) or len(set(hosts)) != len(hosts) or not set(hosts) <= set(HOST_LINKS):
            bad.append(f"{name}: hosts 只能取 {list(HOST_LINKS)} 且不重复")
    return bad


def parse_lock(data: dict) -> dict[str, Plugin]:
    return {
        name: Plugin(name, spec["source"], spec["ref"], spec["commit"], spec["localPath"], tuple(spec["hosts"]))
        for name, spec in data["plugins"].items()
    }


def load_lock(root: Path = ROOT) -> dict[str, Plugin]:
    data = json.loads((root / LOCK_NAME).read_text(encoding="utf-8"))
    bad = lock_problems(data)
    if bad:
        raise ValueError(f"{LOCK_NAME} 不合法：" + "；".join(bad))
    return parse_lock(data)


def expected_host_links(plugins: dict[str, Plugin]) -> dict[str, str]:
    """宿主适配器：仓库相对路径 → 链接文本。与本机家目录无关，CI 可逐字比对。"""
    out = {}
    for p in plugins.values():
        for host in p.hosts:
            d, sub = HOST_LINKS[host]
            out[f"{d}/{p.name}"] = f"../../{HUB_DIR}/{p.name}" + (f"/{sub}" if sub else "")
    return out


def codex_agent_owner(link_text: str) -> str | None:
    """.codex/agents/*.toml 链接指向哪个中枢插件（../../.agents/plugins/<name>/…）。"""
    prefix = f"../../{HUB_DIR}/"
    return link_text[len(prefix):].split("/", 1)[0] if link_text.startswith(prefix) else None


def hub_link_text(p: Plugin, root: Path, home: Path) -> str:
    return os.path.relpath(p.body(home), root / HUB_DIR)


def _git(body: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(body), *args], check=True, capture_output=True, text=True).stdout.strip()


def _norm_url(url: str) -> str:
    return re.sub(r"\.git$", "", url.strip().rstrip("/"))


def body_state(p: Plugin, home: Path) -> tuple[list[str], list[str]]:
    """正文校验：(警告, 违规)。commit 漂移只警告——正文由维护者更新，确认后跑 lock。"""
    body = p.body(home)
    if not body.is_dir():
        return [], [f"{p.name}: 本机没有正文 {body}（跑 sync 按锁克隆）"]
    try:
        origin = _git(body, "remote", "get-url", "origin")
        head = _git(body, "rev-parse", "HEAD")
    except (OSError, subprocess.CalledProcessError):
        return [], [f"{p.name}: {body} 不是带 origin 的 git 仓库"]
    if _norm_url(origin) != _norm_url(p.source):
        return [], [f"{p.name}: 正文来源 {origin} 与锁 {p.source} 不一致"]
    if head != p.commit:
        return [f"{p.name}: 正文 HEAD {head[:7]} ≠ 锁 {p.commit[:7]}（确认后跑 lock 更新锁）"], []
    return [], []


def _ensure_link(path: Path, text: str, actions: list[str], bad: list[str], root: Path) -> None:
    rel = path.relative_to(root)
    if path.is_symlink():
        if os.readlink(path) == text:
            return
        path.unlink()
        path.symlink_to(text)
        actions.append(f"重指 {rel} -> {text}")
    elif path.exists():
        bad.append(f"{rel} 是真实文件/目录，不是链接（复制品？请手动移走）")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(text)
        actions.append(f"新建 {rel} -> {text}")


def _prune(root: Path, keep_hub: set[str], keep_hosts: dict[str, str], keep_codex: set[str],
           actions: list[str], bad: list[str]) -> None:
    """删掉锁外插件的链接；真实文件/目录只报告不删。"""
    for d in (HUB_DIR, *(d for d, _ in HOST_LINKS.values())):
        base = root / d
        for entry in sorted(base.iterdir()) if base.is_dir() else []:
            if entry.name == "README.md" and entry.is_file() and not entry.is_symlink():
                continue
            wanted = entry.name in keep_hub if d == HUB_DIR else f"{d}/{entry.name}" in keep_hosts
            if wanted:
                continue
            if entry.is_symlink():
                entry.unlink()
                actions.append(f"删除 {d}/{entry.name}（不在锁内）")
            else:
                bad.append(f"{d}/{entry.name} 不在锁内且是真实文件/目录，未删除（请手动处理）")
    agents = root / CODEX_AGENTS_DIR
    for entry in sorted(agents.iterdir()) if agents.is_dir() else []:
        if entry.is_symlink() and codex_agent_owner(os.readlink(entry)) not in keep_codex:
            entry.unlink()
            actions.append(f"删除 {CODEX_AGENTS_DIR}/{entry.name}（所属插件不在锁内）")


def _clone(p: Plugin, home: Path, actions: list[str], bad: list[str]) -> None:
    body = p.body(home)
    body.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["git", "clone", "--quiet", "--branch", p.ref, p.source, str(body)],
                       check=True, capture_output=True, text=True)
        if _git(body, "rev-parse", "HEAD") != p.commit:
            _git(body, "checkout", "--quiet", p.commit)
    except (OSError, subprocess.CalledProcessError) as exc:
        bad.append(f"{p.name}: 克隆 {p.source}@{p.commit[:7]} 失败：{getattr(exc, 'stderr', exc)}")
        return
    actions.append(f"克隆 {p.name} {p.source}@{p.commit[:7]} -> {body}")


def sync(root: Path = ROOT, home: Path | None = None) -> tuple[list[str], list[str], list[str]]:
    """按锁建好本机正文与全部链接，删掉锁外插件的链接。返回 (动作, 警告, 违规)。"""
    home = home or Path.home()
    plugins = load_lock(root)
    actions: list[str] = []
    warns: list[str] = []
    bad: list[str] = []
    for p in plugins.values():
        if not p.body(home).exists():
            _clone(p, home, actions, bad)
        w, b = body_state(p, home)
        warns += w
        bad += b
        _ensure_link(root / HUB_DIR / p.name, hub_link_text(p, root, home), actions, bad, root)
    host_links = expected_host_links(plugins)
    for rel, text in host_links.items():
        _ensure_link(root / rel, text, actions, bad, root)
    codex = {p.name for p in plugins.values() if "codex" in p.hosts}
    _prune(root, set(plugins), host_links, codex, actions, bad)
    return actions, warns, bad


def check(root: Path = ROOT, home: Path | None = None, strict: bool = False) -> tuple[list[str], list[str]]:
    """只读校验本机状态：(警告, 违规)。"""
    home = home or Path.home()
    plugins = load_lock(root)
    warns: list[str] = []
    bad: list[str] = []
    for p in plugins.values():
        w, b = body_state(p, home)
        warns += w
        bad += b
        hub = root / HUB_DIR / p.name
        if not hub.is_symlink() or os.readlink(hub) != hub_link_text(p, root, home):
            bad.append(f"{HUB_DIR}/{p.name} 缺失或没有指向 {p.body(home)}（跑 sync）")
    host_links = expected_host_links(plugins)
    for rel, text in host_links.items():
        path = root / rel
        if not path.is_symlink() or os.readlink(path) != text:
            bad.append(f"{rel} 缺失或没有指向 {text}（跑 sync）")
        elif not path.exists():
            bad.append(f"{rel} 是悬空链接（正文缺失？跑 sync）")
    for d in (HUB_DIR, *(d for d, _ in HOST_LINKS.values())):
        base = root / d
        for entry in sorted(base.iterdir()) if base.is_dir() else []:
            if entry.name == "README.md" and entry.is_file() and not entry.is_symlink():
                continue
            if (d == HUB_DIR and entry.name not in plugins) or (d != HUB_DIR and f"{d}/{entry.name}" not in host_links):
                bad.append(f"{d}/{entry.name} 不在锁内（跑 sync 清理）")
    codex = {p.name for p in plugins.values() if "codex" in p.hosts}
    agents = root / CODEX_AGENTS_DIR
    for entry in sorted(agents.iterdir()) if agents.is_dir() else []:
        if not entry.is_symlink():
            continue
        if codex_agent_owner(os.readlink(entry)) not in codex:
            bad.append(f"{CODEX_AGENTS_DIR}/{entry.name} 所属插件不在锁内（跑 sync 清理）")
        elif not entry.exists():
            bad.append(f"{CODEX_AGENTS_DIR}/{entry.name} 是悬空链接（正文缺失？跑 sync）")
    if strict:
        bad += warns
        warns = []
    return warns, bad


def update_lock(root: Path = ROOT, home: Path | None = None, names: list[str] | None = None) -> tuple[list[str], list[str]]:
    """把锁的 commit 更新为本机正文 HEAD；HEAD 必须已在远端，否则别人按锁拉不到。"""
    home = home or Path.home()
    path = root / LOCK_NAME
    data = json.loads(path.read_text(encoding="utf-8"))
    plugins = load_lock(root)
    actions: list[str] = []
    bad: list[str] = []
    for name in names or sorted(plugins):
        p = plugins.get(name)
        if p is None:
            bad.append(f"{name}: 不在锁内")
            continue
        body = p.body(home)
        try:
            head = _git(body, "rev-parse", "HEAD")
            _git(body, "fetch", "--quiet", "origin")
            on_remote = _git(body, "branch", "-r", "--contains", head)
        except (OSError, subprocess.CalledProcessError) as exc:
            bad.append(f"{name}: 读取正文失败：{getattr(exc, 'stderr', exc)}")
            continue
        if not on_remote:
            bad.append(f"{name}: HEAD {head[:7]} 还没推到远端，先推送再更新锁")
            continue
        if head != p.commit:
            data["plugins"][name]["commit"] = head
            actions.append(f"{name}: {p.commit[:7]} -> {head[:7]}")
    if actions:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return actions, bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync", help="按锁克隆缺失正文、建链接、清锁外链接")
    c = sub.add_parser("check", help="只读校验本机状态")
    c.add_argument("--strict", action="store_true", help="commit 漂移也算违规")
    lk = sub.add_parser("lock", help="把锁的 commit 更新为本机正文 HEAD")
    lk.add_argument("names", nargs="*")
    args = ap.parse_args(argv)
    actions: list[str] = []
    warns: list[str] = []
    if args.cmd == "sync":
        actions, warns, bad = sync()
    elif args.cmd == "check":
        warns, bad = check(strict=args.strict)
    else:
        actions, bad = update_lock(names=args.names)
    for line in actions:
        print(f"• {line}")
    for line in warns:
        print(f"⚠ {line}")
    for line in bad:
        print(f"❌ {line}")
    if not bad:
        print(f"✓ 插件与 {LOCK_NAME} 一致（{args.cmd}）")
    return min(len(bad), 255)


if __name__ == "__main__":
    sys.exit(main())
