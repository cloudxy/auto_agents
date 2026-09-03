#!/usr/bin/env python3
from __future__ import annotations
"""
Frontend 前端服务启动入口

使用方式：
    ./run_frontend.py --app admin              # 启动后台管理 (9112)
    ./run_frontend.py --app official           # 启动官方网站 (9113)
    ./run_frontend.py --all                    # 同时启动两者
    ./run_frontend.py --all --env dev          # 透传 REACT_APP_ENV=dev

特性：
- 线程级并发启动，按应用名加前缀输出日志
- 启动前端口预检，占用则报错
- --env 透传到 REACT_APP_ENV，供前端构建区分环境
- --skip-install 跳过 npm install；否则首次启动自动安装
"""
import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            return s.connect_ex(("127.0.0.1", port)) == 0
        except OSError:
            return False


def _ensure_workspaces(skip: bool):
    """npm workspaces 根安装 + shared 先构建（D1/D2：app 经 dist 产物消费 shared）"""
    if skip:
        return
    root = PROJECT_ROOT
    if not os.path.isdir(os.path.join(root, "node_modules")):
        print("安装 workspaces 依赖（根）")
        subprocess.check_call(["npm", "install"], cwd=root)
    dist = os.path.join(root, "frontend", "shared", "dist")
    if not os.path.isdir(dist):
        print("构建 @auto-agents/frontend-shared")
        subprocess.check_call(
            ["npm", "run", "build", "-w", "@auto-agents/frontend-shared"], cwd=root)


def start_app(app_relpath: str, port: int, app_name: str, env_name: str | None):
    full_path = os.path.join(PROJECT_ROOT, app_relpath)
    print(f"Starting {app_name} on port {port}...")

    env = os.environ.copy()
    env["PORT"] = str(port)
    env["BROWSER"] = "none"  # 禁止自动打开浏览器
    if env_name:
        env["REACT_APP_ENV"] = env_name

    try:
        process = subprocess.Popen(
            ["npm", "start"],
            cwd=full_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in iter(process.stdout.readline, ""):
            if line:
                print(f"[{app_name}] {line.rstrip()}")
    except Exception as e:
        print(f"启动 {app_name} 失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="Auto Agents Frontend Manager")
    parser.add_argument("--app", choices=["admin", "official"], help="启动指定应用")
    parser.add_argument("--all", action="store_true", help="启动所有前端应用")
    parser.add_argument("--admin-port", type=int, default=9112, help="管理后台端口")
    parser.add_argument("--official-port", type=int, default=9113, help="官网端口")
    parser.add_argument("--env", choices=["local", "dev", "prod"], default=None,
                        help="透传为 REACT_APP_ENV")
    parser.add_argument("--skip-install", action="store_true", help="跳过 npm install")
    args = parser.parse_args()

    if shutil.which("npm") is None:
        print("未找到 npm，请先安装 Node.js")
        sys.exit(1)

    targets = []
    if args.all or args.app == "admin":
        targets.append(("frontend/admin", args.admin_port, "Admin"))
    if args.all or args.app == "official":
        targets.append(("frontend/official", args.official_port, "Official"))

    if not targets:
        parser.print_help()
        return

    # workspaces 根安装 + shared 构建（幂等，已装/已建则跳过）
    _ensure_workspaces(args.skip_install)

    # 端口预检
    for rel, port, name in targets:
        if _port_in_use(port):
            print(f"端口 {port} ({name}) 已被占用，启动终止")
            sys.exit(1)

    threads = []
    for rel, port, name in targets:
        t = threading.Thread(target=start_app, args=(rel, port, name, args.env), daemon=True)
        t.start()
        threads.append(t)

    try:
        while any(t.is_alive() for t in threads):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n停止前端服务...")


if __name__ == "__main__":
    main()
