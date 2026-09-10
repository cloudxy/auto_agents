"""Frontend 进程入口：python -m scripts.runlib.frontend --app admin"""
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


def _start_app(relpath: str, port: int, name: str, env_name: str | None) -> None:
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["BROWSER"] = "none"
    if env_name:
        env["REACT_APP_ENV"] = env_name
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


def main() -> None:
    reexec_with_venv()
    parser = argparse.ArgumentParser(description="Auto Agents Frontend")
    parser.add_argument("--app", choices=["admin", "official"])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--admin-port", type=int, default=9112)
    parser.add_argument("--official-port", type=int, default=9113)
    parser.add_argument("--env", choices=["local", "dev", "prod"], default=None)
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()
    apply_env(args.env)

    if shutil.which("npm") is None:
        print("未找到 npm，请先安装 Node.js")
        sys.exit(1)

    targets: list[tuple[str, int, str]] = []
    if args.all or args.app == "admin":
        targets.append((APPS["admin"][0], args.admin_port, "Admin"))
    if args.all or args.app == "official":
        targets.append((APPS["official"][0], args.official_port, "Official"))
    if not targets:
        parser.print_help()
        return

    ensure_workspaces(args.skip_install)
    for _, port, name in targets:
        if port_in_use(port):
            print(f"端口 {port} ({name}) 已被占用，启动终止")
            sys.exit(1)

    threads = [
        threading.Thread(target=_start_app, args=(*item, args.env), daemon=True)
        for item in targets
    ]
    for thread in threads:
        thread.start()
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n停止前端服务...")


if __name__ == "__main__":
    main()
