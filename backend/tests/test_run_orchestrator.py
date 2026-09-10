"""scripts.runlib.ctl：解析参数 + 已运行跳过 / 强制重启。"""
from __future__ import annotations

import pytest

from scripts.runlib import ctl, paths


@pytest.fixture
def runmod(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "RUN_DIR", tmp_path)
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
