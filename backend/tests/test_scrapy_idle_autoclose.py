"""IdleAutoClose 收尾窗与 GWT-18.4 离线标注窗分家。

Idle close：连续空闲后 finished（默认 30s），须 < 120 且 ≠ 21600。
Offline annotation：无终态满 120s 才标工人不在线（GWT-18.4）。
21600 只属于 RELAY 探针锁，禁止当任一窗。
"""
from __future__ import annotations

from pathlib import Path

from config import settings

ROOT = Path(__file__).resolve().parents[2]
_PROBE_LOCK = 21600
_CRAWL_BUDGET_SECONDS = 5
_WAIT_BUDGET_SECONDS = 120


def test_idle_close_seconds_not_probe_lock_and_under_120():
    """IdleAutoClose ≠ 21600 且 < 120，才能让 example+httpbin 在提交后 120s 内完成。"""
    idle = int(settings.get("SPIDER_IDLE_CLOSE_SECONDS", 0) or 0)
    probe = int(settings.get("RELAY.PROBE_LOCK_TTL_SECONDS", _PROBE_LOCK) or _PROBE_LOCK)
    assert idle != 21600
    assert idle < 120
    assert idle > 0
    assert probe == 21600
    assert idle != probe

    default_yml = (ROOT / "config" / "scrapy" / "default" / "settings.yml").read_text()
    assert "SPIDER_IDLE_CLOSE_SECONDS: 30" in default_yml
    assert "SPIDER_WORKER_OFFLINE_SECONDS: 120" in default_yml
    assert "SPIDER_IDLE_CLOSE_SECONDS: 120" not in default_yml
    ext_src = (ROOT / "scrapy" / "extensions" / "__init__.py").read_text()
    assert "if not self._has_items:\n            return" not in ext_src
    assert "getint(\"IDLE_CLOSE_SECONDS\", 21600)" not in ext_src
    assert "getint('IDLE_CLOSE_SECONDS', 21600)" not in ext_src
    from backend.services.spider_worker_gate import product_idle_close_seconds
    assert product_idle_close_seconds() != 21600
    assert product_idle_close_seconds() < 120
    assert product_idle_close_seconds() == idle


def test_worker_offline_window_is_120_not_idle_close():
    """GWT-18.4 离线标注窗 = 120；不得复用 IdleAutoClose。"""
    offline = int(settings.get("SPIDER_WORKER_OFFLINE_SECONDS", 0) or 0)
    idle = int(settings.get("SPIDER_IDLE_CLOSE_SECONDS", 0) or 0)
    assert offline == 120
    assert idle != offline
    from backend.services.spider_worker_gate import (
        product_idle_close_seconds,
        product_worker_offline_seconds,
    )
    assert product_worker_offline_seconds() == 120
    assert product_idle_close_seconds() != product_worker_offline_seconds()
    gate_src = (ROOT / "backend" / "services" / "spider_worker_gate.py").read_text()
    assert "window = product_worker_offline_seconds()" in gate_src
    assert "window = product_idle_close_seconds()" not in gate_src


def test_idle_close_plus_crawl_budget_fits_120s():
    """Idle close + 约 5s 爬取预算 < 120s 等待上限（GWT-18.1）。"""
    from backend.services.spider_worker_gate import product_idle_close_seconds
    idle = product_idle_close_seconds()
    assert idle + _CRAWL_BUDGET_SECONDS < _WAIT_BUDGET_SECONDS
