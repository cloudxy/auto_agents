from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

from . import detect
from .catalog import Service
from .paths import ROOT, ensure_run_dir


def spawn(svc: Service, env: str | None) -> bool:
    ensure_run_dir()
    cmd = [sys.executable, "-m", svc.module, *svc.args]
    if env:
        cmd += ["--env", env]
    logf = detect.log_path(svc.name).open("ab")
    print(f"正在启动 {svc.name} ...")
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        stdout=logf,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    detect.write_pid(svc.name, proc.pid)
    if not wait_ready(svc, proc):
        print(f"{svc.name} 启动失败，见 {detect.log_path(svc.name)}")
        return False
    extra = f"  {svc.url}" if svc.url else ""
    print(f"{svc.name} 已启动{extra}  log={detect.log_path(svc.name)}")
    return True


def wait_ready(svc: Service, proc: subprocess.Popen, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        if svc.port:
            if detect.port_in_use(svc.port):
                return True
        elif detect.pid_alive(proc.pid):
            time.sleep(0.4)
            return proc.poll() is None
        time.sleep(0.2)
    return proc.poll() is None


def kill(svc: Service) -> None:
    pid = detect.read_pid(svc.name)
    pids = [pid] if pid else []
    if svc.port:
        for extra in detect.pids_on_port(svc.port):
            if extra not in pids:
                pids.append(extra)
    if not pids:
        detect.clear_pid(svc.name)
        return
    print(f"正在停止 {svc.name} ...")
    _signal_all(pids, signal.SIGTERM)
    deadline = time.time() + 5
    while time.time() < deadline:
        alive = any(detect.pid_alive(p) for p in pids)
        busy = bool(svc.port and detect.port_in_use(svc.port))
        if not alive and not busy:
            break
        time.sleep(0.1)
    _signal_all([p for p in pids if detect.pid_alive(p)], signal.SIGKILL)
    detect.clear_pid(svc.name)
    print(f"{svc.name} 已停止")


def _signal_all(pids: list[int], sig: int) -> None:
    for pid in pids:
        try:
            os.killpg(pid, sig)
        except OSError:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
