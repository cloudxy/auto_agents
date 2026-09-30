"""Scrapy 出站守卫中间件（审计 BUG-22 / F4-1 / P0-8 回归）

约定同 test_scrapy_retry_middleware：不启动引擎，importlib 加载 scrapy 侧代码。
DNS 由 conftest 的出站 DNS 桩接管（测试不出网）。
"""
import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SCRAPY_DIR = str(Path(__file__).resolve().parents[2] / "scrapy")
if _SCRAPY_DIR not in sys.path:
    sys.path.insert(0, _SCRAPY_DIR)
os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "settings")


def _mw(**kw):
    return importlib.import_module("middlewares").OutboundGuardMiddleware(**kw)


def _req(url: str):
    return importlib.import_module("scrapy.http").Request(url, meta={"task_id": 9})


def _ignore():
    return importlib.import_module("scrapy.exceptions").IgnoreRequest


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8080/admin",
    "http://169.254.169.254/latest/meta-data/iam/",
    "http://10.0.0.8/",
    "http://127.0.0.1.nip.io/",
    "http://[::1]/",
    "http://2130706433/",
    "file:///etc/passwd",
    "ftp://files.example.com/x",
])
def test_blocks_internal_and_non_http(url):
    with pytest.raises(_ignore()):
        _mw().process_request(_req(url), MagicMock(name="spider"))


def test_allows_public_site():
    assert _mw().process_request(_req("https://example.com/list?p=2"), MagicMock()) is None


def test_redirect_hop_rechecked():
    """重定向产物是新 Request，会再次经过 process_request：跳内网即拒"""
    mw = _mw()
    assert mw.process_request(_req("https://example.com/r"), MagicMock()) is None
    with pytest.raises(_ignore()):
        mw.process_request(_req("http://10.1.1.1/after-redirect"), MagicMock())


def test_allowlisted_local_target_for_dev():
    assert _mw(allowed_hosts=["localhost"]).process_request(
        _req("http://localhost:9000/fixture"), MagicMock()) is None


def test_guard_is_first_downloader_middleware():
    settings = importlib.import_module("settings")
    # None = 禁用（如被替换掉的原生 RobotsTxtMiddleware），不参与排序
    order = sorted(((k, v) for k, v in settings.DOWNLOADER_MIDDLEWARES.items() if v is not None),
                   key=lambda kv: kv[1])
    assert order[0][0] == "middlewares.OutboundGuardMiddleware"
    assert settings.OUTBOUND_GUARD_ENABLED is True
