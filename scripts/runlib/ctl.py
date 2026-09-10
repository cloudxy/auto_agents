from __future__ import annotations

import argparse
import subprocess
import sys

from . import detect, process
from .catalog import SERVICES, resolve_targets
from .paths import ROOT
from .venv import reexec_with_venv

ACTIONS = ("start", "stop", "restart", "reload", "status")


def parse_argv(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Auto Agents 统一启停",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="默认 start 全部。setup 一键初始化。已运行则跳过；restart/reload 强制重启。",
    )
    parser.add_argument("--env", choices=["local", "dev", "prod"], default=None)
    parser.add_argument("--list", action="store_true", help="列出爬虫后退出")
    parser.add_argument("words", nargs="*", help="动作和/或服务名")
    ns = parser.parse_args(argv)

    words = list(ns.words)
    if words and words[0] == "setup":
        ns.action = "setup"
        ns.targets = []
        return ns

    action = "start"
    raw = words[1:] if words and words[0] in ACTIONS else words
    if words and words[0] in ACTIONS:
        action = "restart" if words[0] == "reload" else words[0]
    if not raw:
        raw = ["all"]
    try:
        ns.targets = resolve_targets(raw)
    except ValueError as exc:
        parser.error(f"未知服务或动作: {exc}")
    ns.action = action
    return ns


def is_running(name: str) -> bool:
    return detect.is_running(name, SERVICES[name].port)


def _spawn(name: str, env: str | None) -> bool:
    return process.spawn(SERVICES[name], env)


def _kill(name: str) -> None:
    process.kill(SERVICES[name])


def _prepare_frontend(targets: list[str]) -> None:
    if any(name in ("admin", "official") for name in targets):
        from .frontend import ensure_workspaces
        ensure_workspaces(skip=False)


def cmd_start(targets: list[str], env: str | None) -> int:
    _prepare_frontend(targets)
    ok = True
    for name in targets:
        if is_running(name):
            print(f"{name} 已经启动，跳过")
            continue
        if not _spawn(name, env):
            ok = False
    return 0 if ok else 1


def cmd_stop(targets: list[str]) -> int:
    for name in reversed(targets):
        if not is_running(name):
            print(f"{name} 未在运行，无需停止")
            continue
        _kill(name)
    return 0


def cmd_restart(targets: list[str], env: str | None) -> int:
    cmd_stop(targets)
    return cmd_start(targets, env)


def cmd_status(targets: list[str]) -> int:
    for name in targets:
        svc = SERVICES[name]
        state = "运行中" if is_running(name) else "未运行"
        bits = [name, state]
        pid = detect.read_pid(name)
        if pid:
            bits.append(f"pid={pid}")
        if svc.url:
            bits.append(svc.url)
        print("  ".join(bits))
    return 0


def list_spiders(env: str | None) -> int:
    cmd = [sys.executable, "-m", "scripts.runlib.spider", "--list"]
    if env:
        cmd += ["--env", env]
    return subprocess.call(cmd, cwd=ROOT)


def main() -> int:
    reexec_with_venv()
    ns = parse_argv()
    if ns.list:
        return list_spiders(ns.env)
    if ns.action == "setup":
        return subprocess.call(["bash", str(ROOT / "init_project.sh")], cwd=ROOT)
    dispatch = {
        "start": lambda: cmd_start(ns.targets, ns.env),
        "stop": lambda: cmd_stop(ns.targets),
        "restart": lambda: cmd_restart(ns.targets, ns.env),
        "status": lambda: cmd_status(ns.targets),
    }
    return dispatch[ns.action]()
