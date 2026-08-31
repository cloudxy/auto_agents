#!/usr/bin/env python3
from __future__ import annotations
"""
Auto Agents 统一入口 —— 纯 orchestrator

职责：fork 三个独立启动脚本为子进程，统一日志 + 信号管理。
      不做环境自愈、不跑迁移、不装依赖（初始化请用 scripts/bootstrap-db.sh）。

使用方式：
    python run.py all                       # 同时起 backend + frontend
    python run.py all --env dev
    python run.py backend                   # 只起 backend
    python run.py spider --list
    python run.py frontend --app admin
"""
import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

_processes: list[subprocess.Popen] = []


def _stream(process: subprocess.Popen, prefix: str):
    for line in iter(process.stdout.readline, ""):
        if line:
            print(f"[{prefix}] {line.rstrip()}")


def _spawn(script: str, extra_args: list[str], prefix: str):
    cmd = [sys.executable, os.path.join(PROJECT_ROOT, script)] + extra_args
    print(f"Launching {prefix}: {' '.join(cmd)}")
    p = subprocess.Popen(
        cmd,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,  # 新进程组便于整组 kill
    )
    _processes.append(p)
    t = threading.Thread(target=_stream, args=(p, prefix), daemon=True)
    t.start()
    return p, t


def _port_ok(port: int, name: str) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        if s.connect_ex(("127.0.0.1", port)) == 0:
            print(f"端口 {port} ({name}) 已占用")
            return False
    return True


def _shutdown(_sig=None, _frame=None):
    print("\n正在关闭所有子进程...")
    for p in _processes:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except Exception:
            pass
    # 给 3 秒退出时间
    t0 = time.time()
    while time.time() - t0 < 3 and any(p.poll() is None for p in _processes):
        time.sleep(0.1)
    for p in _processes:
        if p.poll() is None:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except Exception:
                pass
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Auto Agents 统一入口")
    sub = parser.add_subparsers(dest="command", required=True)

    p_all = sub.add_parser("all", help="启动 backend + 两个前端")
    p_all.add_argument("--env", choices=["local", "dev", "prod"], default=None)

    p_be = sub.add_parser("backend", help="只启 backend")
    p_be.add_argument("--env", choices=["local", "dev", "prod"], default=None)
    p_be.add_argument("--no-reload", action="store_true")
    p_be.add_argument("--port", type=int, default=None)

    p_sp = sub.add_parser("spider", help="只启 scrapy")
    p_sp.add_argument("--env", choices=["local", "dev", "prod"], default=None)
    p_sp.add_argument("--spider", type=str, default=None)
    p_sp.add_argument("--list", action="store_true")

    p_fe = sub.add_parser("frontend", help="只启 frontend")
    p_fe.add_argument("--env", choices=["local", "dev", "prod"], default=None)
    p_fe.add_argument("--app", choices=["admin", "official"], default=None)
    p_fe.add_argument("--all", action="store_true")

    args = parser.parse_args()
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    if args.command == "backend":
        extra = []
        if args.env: extra += ["--env", args.env]
        if args.no_reload: extra += ["--no-reload"]
        if args.port: extra += ["--port", str(args.port)]
        _spawn("run_backend.py", extra, "Backend")

    elif args.command == "spider":
        extra = []
        if args.env: extra += ["--env", args.env]
        if args.list: extra += ["--list"]
        if args.spider: extra += ["--spider", args.spider]
        _spawn("run_spider.py", extra, "Spider")

    elif args.command == "frontend":
        extra = []
        if args.env: extra += ["--env", args.env]
        if args.all: extra += ["--all"]
        if args.app: extra += ["--app", args.app]
        _spawn("run_frontend.py", extra, "Frontend")

    elif args.command == "all":
        _port_ok(9111, "Backend") or _port_ok(9112, "Admin") or _port_ok(9113, "Official")
        be = ["--no-reload"]
        fe = ["--all"]
        sp = []
        if args.env:
            be += ["--env", args.env]
            fe += ["--env", args.env]
            sp += ["--env", args.env]
        _spawn("run_backend.py", be, "Backend")
        time.sleep(2)  # 给 backend 起来的时间
        # 常驻爬虫 Worker：监听各 <spider>:start_urls，消费管理后台投递的任务（数据闭环的执行端）
        _spawn("run_spider.py", sp, "Spider")
        _spawn("run_frontend.py", fe, "Frontend")
        print("\n✅ 全栈已启动 (Ctrl+C 停止)\n")

    try:
        while any(p.poll() is None for p in _processes):
            time.sleep(1)
    except KeyboardInterrupt:
        _shutdown()


if __name__ == "__main__":
    main()
