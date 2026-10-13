"""Frontend 进程入口：python -m scripts.runlib.frontend --app admin（Vite 开发服务器）"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time

from .detect import port_in_use
from .paths import ROOT
from .venv import apply_env, reexec_with_venv

APPS = {
    "admin": ("frontend/admin", 9112),
    "official": ("frontend/official", 9113),
}
_WILDCARD_HOSTS = {"", "0.0.0.0", "::"}


def ensure_workspaces(skip: bool) -> None:
    if skip:
        return
    if not (ROOT / "node_modules").is_dir():
        print("安装 workspaces 依赖（根）")
        subprocess.check_call(["npm", "install"], cwd=ROOT)
    dist = ROOT / "frontend" / "shared" / "dist"
    if not dist.is_dir():
        print("构建 @auto-agents/frontend-shared")
        subprocess.check_call(
            ["npm", "run", "build", "-w", "@auto-agents/frontend-shared"], cwd=ROOT,
        )


def api_proxy_target() -> str:
    """dev 服务器 /api 反代目标：跟随 config 的 API.HOST/PORT（监听全部网卡时走本机回环）。"""
    from config import settings

    host = str(settings.API.HOST)
    host = "127.0.0.1" if host in _WILDCARD_HOSTS else host
    return f"http://{f'[{host}]' if ':' in host else host}:{settings.API.PORT}"


def app_env(port: int, env_name: str | None, proxy_target: str) -> dict[str, str]:
    """子进程环境：vite.config.mts 读 PORT 与 API_PROXY_TARGET（已显式设置的 API_PROXY_TARGET 优先）。"""
    env = os.environ.copy()
    env["PORT"] = str(port)
    env.setdefault("API_PROXY_TARGET", proxy_target)
    if env_name:
        env["REACT_APP_ENV"] = env_name
    return env


def _start_app(relpath: str, name: str, env: dict[str, str]) -> None:
    proc = subprocess.Popen(
        ["npm", "start"],
        cwd=ROOT / relpath,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert proc.stdout is not None
    for line in iter(proc.stdout.readline, ""):
        if line:
            print(f"[{name}] {line.rstrip()}")


def _parse_args() -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = argparse.ArgumentParser(description="Auto Agents Frontend")
    parser.add_argument("--app", choices=sorted(APPS))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--admin-port", type=int, default=APPS["admin"][1])
    parser.add_argument("--official-port", type=int, default=APPS["official"][1])
    parser.add_argument("--env", choices=["local", "dev", "prod"], default=None)
    parser.add_argument("--skip-install", action="store_true")
    return parser, parser.parse_args()


def _select_targets(args: argparse.Namespace) -> list[tuple[str, int, str]]:
    targets: list[tuple[str, int, str]] = []
    if args.all or args.app == "admin":
        targets.append((APPS["admin"][0], args.admin_port, "Admin"))
    if args.all or args.app == "official":
        targets.append((APPS["official"][0], args.official_port, "Official"))
    return targets


def _serve(targets: list[tuple[str, int, str]], env_name: str | None) -> None:
    proxy_target = api_proxy_target()
    threads = [
        threading.Thread(
            target=_start_app, args=(relpath, name, app_env(port, env_name, proxy_target)), daemon=True,
        )
        for relpath, port, name in targets
    ]
    for thread in threads:
        thread.start()
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n停止前端服务...")


def main() -> None:
    reexec_with_venv()
    parser, args = _parse_args()
    apply_env(args.env)

    if shutil.which("npm") is None:
        print("未找到 npm，请先安装 Node.js")
        sys.exit(1)

    targets = _select_targets(args)
    if not targets:
        parser.print_help()
        return

    ensure_workspaces(args.skip_install)
    for _, port, name in targets:
        if port_in_use(port):
            print(f"端口 {port} ({name}) 已被占用，启动终止")
            sys.exit(1)
    _serve(targets, args.env)


if __name__ == "__main__":
    main()
