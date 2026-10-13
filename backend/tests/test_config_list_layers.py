"""配置分层守护：merge_enabled 下列表键不得跨层重复定义 + 各环境 CORS 实际生效值。

config/__init__.py 开了 Dynaconf merge_enabled：同一列表键在 config/default 与 config/<env>
都出现时，结果是两层「追加」而不是环境层覆盖。曾因此让生产 CORS 放行 default 的
localhost 来源、ALLOW_HEADERS 仍含 "*"——而 prod/web.yml 注释写的是「覆盖」。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from backend.app.cors_check import cors_config_warnings

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "config"
ENVS = ("local", "dev", "prod")


def _list_keys(data, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower().startswith("dynaconf"):
                continue
            path = f"{prefix}.{key}" if prefix else str(key)
            keys |= {path} if isinstance(value, list) else _list_keys(value, path)
    return keys


def _layer_list_keys(*dirs: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for d in dirs:
        for f in sorted(d.glob("*.yml")):
            for key in _list_keys(yaml.safe_load(f.read_text(encoding="utf-8")) or {}):
                found[key] = f
    return found


@pytest.mark.parametrize("env", ENVS)
def test_no_list_key_defined_in_both_default_and_env_layer(env):
    base = _layer_list_keys(CONFIG / "default", CONFIG / "scrapy" / "default")
    layer = _layer_list_keys(CONFIG / env, CONFIG / "scrapy" / env)
    clash = sorted(f"{k}（{base[k].relative_to(REPO_ROOT)} + {layer[k].relative_to(REPO_ROOT)}）"
                   for k in base.keys() & layer.keys())
    assert not clash, f"列表键跨层重复定义会被追加合并而非覆盖: {clash}"


def _resolved_cors(env: str) -> dict:
    """子进程按指定 APP_ENV 加载配置（settings 是进程级单例，不能在本进程切环境）"""
    code = "import json; from config import settings; print(json.dumps(settings.CORS.to_dict()))"
    environ = {k: v for k, v in os.environ.items() if not k.startswith("AUTO_AGENTS_CORS")}
    environ["APP_ENV"] = env
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, env=environ,
                         capture_output=True, text=True, check=True).stdout
    return yaml.safe_load(out.strip().splitlines()[-1])


def test_prod_cors_has_no_dev_origins_or_wildcard_headers():
    cors = _resolved_cors("prod")
    assert cors["ORIGINS"] == []
    assert "*" not in cors["ALLOW_HEADERS"]
    assert cors_config_warnings(cors, "prod") == []


def test_local_cors_keeps_dev_servers_without_duplicates():
    origins = _resolved_cors("local")["ORIGINS"]
    assert "http://localhost:9112" in origins and "http://127.0.0.1:9113" in origins
    assert len(origins) == len(set(origins))


@pytest.mark.parametrize(("origins", "env", "needle"), [
    (["https://your-domain.com"], "prod", "占位域名"),
    (["https://admin.example.com"], "local", "占位域名"),
    (["http://localhost:9112"], "prod", "本机来源"),
    (["*"], "dev", "\"*\""),
])
def test_cors_warnings_flag_risky_origins(origins, env, needle):
    warnings = cors_config_warnings({"ORIGINS": origins, "ALLOW_CREDENTIALS": True}, env)
    assert any(needle in w for w in warnings), warnings


def test_cors_warnings_match_hostnames_not_substrings():
    cors = {"ORIGINS": ["https://myexample.com", "https://notlocalhost.io"], "ALLOW_CREDENTIALS": True}
    assert cors_config_warnings(cors, "prod") == []


@pytest.mark.parametrize(("raw", "expected"), [
    ("https://a.example.net", ["https://a.example.net"]),
    ("https://a.example.net, https://b.example.net,", ["https://a.example.net", "https://b.example.net"]),
    (["https://a.example.net"], ["https://a.example.net"]),
    (None, []),
])
def test_as_str_list_never_splits_strings_into_characters(raw, expected):
    from backend.app.cors_check import as_str_list

    assert as_str_list(raw) == expected


def test_bare_string_origins_env_still_allows_exact_origin_only():
    """AUTO_AGENTS_CORS__ORIGINS=https://a,https://b（未写成 TOML 列表）：Dynaconf 给 str，
    中间件不得把它拆成单字符（全部跨域被拒），也不得退回 str 子串匹配（https://a.co 放行）"""
    from starlette.middleware.cors import CORSMiddleware

    from backend.app.cors_check import as_str_list

    origins = as_str_list("https://admin.foo.example.net,https://www.foo.example.net")
    mw = CORSMiddleware(app=lambda *a: None, allow_origins=origins, allow_credentials=True)
    assert mw.is_allowed_origin("https://admin.foo.example.net")
    assert mw.is_allowed_origin("https://www.foo.example.net")
    assert not mw.is_allowed_origin("https://admin.foo.example.ne")
