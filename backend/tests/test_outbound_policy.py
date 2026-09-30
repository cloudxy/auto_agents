"""租户可填任意采集地址，平台强制出站边界（决策 D7 = B，连带 D8，2026-09-29「按照建议做」）

- 内网 / 元数据地址拒绝（批次 1 已落地，test_scrapy_outbound_guard.py）
- 平台可配置禁采域名（OUTBOUND.BLOCKED_DOMAINS）：所有出站路径统一经 check_url 拒绝
- 租户填地址的通用 / 流程爬虫默认遵守 robots.txt（D8），自动限速、单域并发更低；
  站点级豁免走 OUTBOUND.ROBOTS_EXEMPT_DOMAINS
"""
from __future__ import annotations

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


@pytest.fixture
def outbound_cfg():
    from config import settings

    keys = ("OUTBOUND.BLOCKED_DOMAINS", "OUTBOUND.ROBOTS_EXEMPT_DOMAINS")
    originals = {k: settings.get(k) for k in keys}
    settings.set("OUTBOUND.BLOCKED_DOMAINS", ["*.blocked.test", "evil.test"])
    settings.set("OUTBOUND.ROBOTS_EXEMPT_DOMAINS", ["partner.test"])
    yield
    for k, v in originals.items():
        settings.set(k, v)


@pytest.mark.parametrize("url", ["https://evil.test/a", "https://www.blocked.test/list"])
def test_blocked_domains_rejected_everywhere(outbound_cfg, url):
    from platform_core.outbound_guard import OutboundBlocked, check_url

    with pytest.raises(OutboundBlocked) as exc:
        check_url(url, resolve=False)
    assert "不在平台允许的采集范围" in exc.value.message


def test_other_public_domains_still_allowed(outbound_cfg):
    from platform_core.outbound_guard import check_url

    check_url("https://news.example.com/list", resolve=False)
    check_url("https://blocked.test.example.com/", resolve=False)  # 只是名字里带，不是子域


@pytest.mark.parametrize("module, cls", [("spiders.generic", "GenericSpider"),
                                         ("spiders.flow_generic", "FlowGenericSpider")])
def test_tenant_url_spiders_are_polite_by_default(module, cls):
    spider_cls = getattr(importlib.import_module(module), cls)
    cs = spider_cls.custom_settings or {}
    assert cs.get("ROBOTSTXT_OBEY") is True
    assert cs.get("AUTOTHROTTLE_ENABLED") is True
    assert int(cs.get("CONCURRENT_REQUESTS_PER_DOMAIN", 99)) <= 4


def test_robots_exempt_domain_marks_request(outbound_cfg, monkeypatch):
    mw = importlib.import_module("middlewares").OutboundGuardMiddleware()
    monkeypatch.setattr(mw, "_verdict", lambda url: "")
    Request = importlib.import_module("scrapy.http").Request
    exempt = Request("https://partner.test/a")
    normal = Request("https://news.example.com/a")
    mw.process_request(exempt, MagicMock())
    mw.process_request(normal, MagicMock())
    assert exempt.meta.get("dont_obey_robotstxt") is True
    assert "dont_obey_robotstxt" not in normal.meta
