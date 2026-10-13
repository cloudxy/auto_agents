"""scripts.runlib.frontend：Vite 开发服务器子进程的端口与 /api 反代目标。"""
from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest

import config
from scripts.runlib import frontend


def test_app_env_passes_port_proxy_target_and_env(monkeypatch):
    monkeypatch.delenv("API_PROXY_TARGET", raising=False)
    env = frontend.app_env(9112, "local", "http://127.0.0.1:9111")
    assert env["PORT"] == "9112"
    assert env["API_PROXY_TARGET"] == "http://127.0.0.1:9111"
    assert env["REACT_APP_ENV"] == "local"


def test_app_env_keeps_explicit_proxy_target(monkeypatch):
    monkeypatch.setenv("API_PROXY_TARGET", "http://10.0.0.5:9000")
    env = frontend.app_env(9113, None, "http://127.0.0.1:9111")
    assert env["PORT"] == "9113"
    assert env["API_PROXY_TARGET"] == "http://10.0.0.5:9000"


@pytest.mark.parametrize(("host", "expected"), [
    ("127.0.0.1", "http://127.0.0.1:9111"),
    ("0.0.0.0", "http://127.0.0.1:9111"),
    ("::", "http://127.0.0.1:9111"),
    ("::1", "http://[::1]:9111"),
    ("10.0.0.8", "http://10.0.0.8:9111"),
])
def test_api_proxy_target_follows_api_config(monkeypatch, host, expected):
    fake = SimpleNamespace(API=SimpleNamespace(HOST=host, PORT=9111))
    monkeypatch.setattr(config, "settings", fake)
    assert frontend.api_proxy_target() == expected


def test_select_targets_uses_catalog_ports():
    args = argparse.Namespace(all=True, app=None, admin_port=9112, official_port=9113)
    assert frontend._select_targets(args) == [
        ("frontend/admin", 9112, "Admin"),
        ("frontend/official", 9113, "Official"),
    ]
    one = argparse.Namespace(all=False, app="official", admin_port=1, official_port=2)
    assert frontend._select_targets(one) == [("frontend/official", 2, "Official")]
