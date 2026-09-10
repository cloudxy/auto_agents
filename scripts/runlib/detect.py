from __future__ import annotations

import os
import socket
import subprocess

from . import paths


def pid_path(name: str):
    return paths.RUN_DIR / f"{name}.pid"


def log_path(name: str):
    return paths.RUN_DIR / f"{name}.log"


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_pid(name: str) -> int | None:
    path = pid_path(name)
    if not path.exists():
        return None
    try:
        pid = int(path.read_text().strip())
    except ValueError:
        return None
    if not pid_alive(pid):
        path.unlink(missing_ok=True)
        return None
    return pid


def write_pid(name: str, pid: int) -> None:
    pid_path(name).write_text(str(pid))


def clear_pid(name: str) -> None:
    pid_path(name).unlink(missing_ok=True)


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        try:
            return sock.connect_ex((host, port)) == 0
        except OSError:
            return False


def pids_on_port(port: int) -> list[int]:
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f"tcp:{port}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    pids: list[int] = []
    for line in out.split():
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return pids


def is_running(name: str, port: int | None) -> bool:
    if read_pid(name) is not None:
        return True
    return bool(port and port_in_use(port))
