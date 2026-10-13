"""scripts.runlib.ctl：解析参数 + 已运行跳过 / 强制重启。"""
from __future__ import annotations

import pytest

from scripts.runlib import ctl, paths


@pytest.fixture
def runmod(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "RUN_DIR", tmp_path)
    # start / restart 会先跑 .agents → 能力市场同步（子进程连真库）。单测只验编排，
    # 同步打桩；原先未打桩，每跑一次测试就往开发库写 3 次同步（2026-09-29 实证）
    synced: list = []
    monkeypatch.setattr(ctl, "cmd_sync_agents", lambda env: synced.append(env) or 0)
    ctl._test_synced = synced
    return ctl


def test_parse_default_is_start_all(runmod):
    ns = runmod.parse_argv([])
    assert ns.action == "start"
    assert ns.targets == ["backend", "spider", "admin", "official"]


def test_parse_start_stop_restart_reload(runmod):
    assert runmod.parse_argv(["start"]).action == "start"
    assert runmod.parse_argv(["stop"]).action == "stop"
    assert runmod.parse_argv(["restart"]).action == "restart"
    assert runmod.parse_argv(["reload"]).action == "restart"


def test_parse_service_as_first_token(runmod):
    ns = runmod.parse_argv(["backend"])
    assert ns.action == "start"
    assert ns.targets == ["backend"]


def test_parse_all_alias(runmod):
    ns = runmod.parse_argv(["all"])
    assert ns.action == "start"
    assert ns.targets == ["backend", "spider", "admin", "official"]


def test_parse_frontend_expands(runmod):
    ns = runmod.parse_argv(["stop", "frontend"])
    assert ns.action == "stop"
    assert ns.targets == ["admin", "official"]


def test_parse_setup(runmod):
    ns = runmod.parse_argv(["setup"])
    assert ns.action == "setup"
    assert ns.targets == []


def test_parse_env(runmod):
    ns = runmod.parse_argv(["--env", "prod", "restart", "backend"])
    assert ns.env == "prod"
    assert ns.action == "restart"
    assert ns.targets == ["backend"]


def test_is_running_stale_pid(runmod, tmp_path, monkeypatch):
    from scripts.runlib import detect
    monkeypatch.setattr(detect, "port_in_use", lambda port, host="127.0.0.1": False)
    (tmp_path / "backend.pid").write_text("99999999")
    assert runmod.is_running("backend") is False


def test_start_skips_when_running(runmod, monkeypatch, capsys):
    monkeypatch.setattr(runmod, "is_running", lambda name: True)
    spawned = []
    monkeypatch.setattr(runmod, "_spawn", lambda name, env: spawned.append(name))
    assert runmod.cmd_start(["backend"], env=None) == 0
    assert spawned == []
    assert "已经启动" in capsys.readouterr().out


def test_start_spawns_when_stopped(runmod, monkeypatch):
    monkeypatch.setattr(runmod, "is_running", lambda name: False)
    spawned = []
    monkeypatch.setattr(runmod, "_spawn", lambda name, env: spawned.append(name) or True)
    assert runmod.cmd_start(["backend"], env=None) == 0
    assert spawned == ["backend"]
    assert runmod._test_synced == [None]  # 启动前同步仍会被调用（行为不变，只是不连真库）


def test_stop_noop_when_stopped(runmod, monkeypatch, capsys):
    monkeypatch.setattr(runmod, "is_running", lambda name: False)
    killed = []
    monkeypatch.setattr(runmod, "_kill", lambda name: killed.append(name))
    assert runmod.cmd_stop(["spider"]) == 0
    assert killed == []
    assert "未在运行" in capsys.readouterr().out


def test_restart_stops_then_starts(runmod, monkeypatch):
    state = {"running": True}
    monkeypatch.setattr(runmod, "is_running", lambda name: state["running"])
    monkeypatch.setattr(runmod, "_kill", lambda name: state.__setitem__("running", False))
    spawned = []
    monkeypatch.setattr(runmod, "_spawn", lambda name, env: spawned.append(name) or True)
    assert runmod.cmd_restart(["backend"], env="local") == 0
    assert spawned == ["backend"]


def test_spawn_detaches_stdin_from_terminal(tmp_path, monkeypatch):
    """后台服务不读启动它的终端：Vite 开发服务器读 stdin 做快捷键，继承终端会吞掉 shell 输入，
    一行 q 就让前端退出。spawn 必须把 stdin 接到 DEVNULL。"""
    import subprocess

    from scripts.runlib import detect, process
    from scripts.runlib.catalog import Service

    captured: dict = {}

    class _Proc:
        pid = 4321

    def _popen(cmd, **kwargs):
        captured.update(kwargs)
        return _Proc()

    monkeypatch.setattr(process.subprocess, "Popen", _popen)
    monkeypatch.setattr(process, "ensure_run_dir", lambda: None)
    monkeypatch.setattr(detect, "log_path", lambda name: tmp_path / f"{name}.log")
    monkeypatch.setattr(detect, "write_pid", lambda name, pid: None)
    monkeypatch.setattr(process, "wait_ready", lambda svc, proc: True)
    svc = Service("admin", "scripts.runlib.frontend", ("--app", "admin"), 9112, "http://127.0.0.1:9112")
    assert process.spawn(svc, None) is True
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["start_new_session"] is True
