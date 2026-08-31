"""scrapy RetryMiddleware 单测（P0-1：重试上限 + 429 槽位退避）

约定：不启动 Scrapy 引擎；scrapy 侧代码经 importlib 加载（B2 红线：
backend 包内不允许行首 import scrapy，测试亦遵守，同 test_spider_generic_spider）。
"""
import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

# scrapy 项目根加入路径（与 run_spider.py 相同的加载方式）
_SCRAPY_DIR = str(Path(__file__).resolve().parents[2] / "scrapy")
if _SCRAPY_DIR not in sys.path:
    sys.path.insert(0, _SCRAPY_DIR)
import os  # noqa: E402

os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "settings")


def _load_retry_mw():
    return importlib.import_module("middlewares").RetryMiddleware


def _scrapy_http():
    return importlib.import_module("scrapy.http")


def _mw(max_retries: int = 3, backoff_base: float = 5.0):
    return _load_retry_mw()(max_retries=max_retries, backoff_base=backoff_base)


def _slot_spider(delay: float = 1.0):
    """构造带 downloader.slots 的假 spider（槽位延迟可被中间件上调）"""
    slot = MagicMock()
    slot.delay = delay
    downloader = MagicMock()
    downloader.slots = {"example.com": slot}
    engine = MagicMock()
    engine.downloader = downloader
    crawler = MagicMock()
    crawler.engine = engine
    spider = MagicMock()
    spider.crawler = crawler
    return spider, slot


# ---------------- 基础语义 ----------------
def test_non_retry_status_passes_through():
    http = _scrapy_http()
    mw = _mw()
    resp = http.Response("https://example.com", status=200)
    out = mw.process_response(http.Request("https://example.com"), resp, MagicMock())
    assert out is resp


def test_first_retry_increments_retry_times_and_dont_filter():
    http = _scrapy_http()
    mw = _mw()
    req = http.Request("https://example.com", meta={})
    out = mw.process_response(req, http.Response("https://example.com", status=503), MagicMock())
    assert out is not req
    assert out.url == "https://example.com"
    assert out.meta["retry_times"] == 1
    assert out.dont_filter is True


def test_retry_cap_reached_returns_response():
    """达到上限后放行响应（P0-1 核心：不再无限重试）"""
    http = _scrapy_http()
    mw = _mw(max_retries=3)
    resp = http.Response("https://example.com", status=429)
    req = http.Request("https://example.com", meta={"retry_times": 3})
    out = mw.process_response(req, resp, MagicMock())
    assert out is resp  # 原样放行，不再产生新请求


def test_dont_retry_meta_respected():
    http = _scrapy_http()
    mw = _mw()
    resp = http.Response("https://example.com", status=500)
    req = http.Request("https://example.com", meta={"dont_retry": True})
    assert mw.process_response(req, resp, MagicMock()) is resp


# ---------------- 429 槽位退避 ----------------
def test_429_bumps_download_slot_delay_exponentially_with_cap():
    http = _scrapy_http()
    mw = _mw(max_retries=5, backoff_base=5.0)

    spider, slot = _slot_spider(delay=1.0)
    req = http.Request("https://example.com", meta={"download_slot": "example.com"})
    mw.process_response(req, http.Response("https://example.com", status=429), spider)
    assert slot.delay == 5.0  # max(1.0, 5*2^0)

    req2 = http.Request("https://example.com", meta={"download_slot": "example.com", "retry_times": 1})
    mw.process_response(req2, http.Response("https://example.com", status=429), spider)
    assert slot.delay == 10.0  # 5*2^1

    req5 = http.Request("https://example.com", meta={"download_slot": "example.com", "retry_times": 4})
    mw.process_response(req5, http.Response("https://example.com", status=429), spider)
    assert slot.delay == 60.0  # 5*2^4=80 → 封顶 60

    # retry_times 达到 max_retries 时：直接放行（不再调整延迟、不再产生新请求）
    resp = http.Response("https://example.com", status=429)
    req6 = http.Request("https://example.com", meta={"download_slot": "example.com", "retry_times": 5})
    assert mw.process_response(req6, resp, spider) is resp


def test_429_without_slot_access_still_retries_bounded():
    """取不到下载槽位（异常形态 spider）：退避跳过，重试上限仍兜底"""
    http = _scrapy_http()
    mw = _mw(max_retries=2)
    bare_spider = MagicMock(spec=[])  # 无 crawler 属性
    req = http.Request("https://example.com", meta={})
    out = mw.process_response(req, http.Response("https://example.com", status=429), bare_spider)
    assert out.meta["retry_times"] == 1


# ---------------- from_crawler 装配 ----------------
def test_from_crawler_reads_retry_times_setting():
    mw_mod = importlib.import_module("middlewares")
    crawler = MagicMock()
    crawler.settings.getint.return_value = 7
    crawler.settings.getfloat.return_value = 3.0
    mw = mw_mod.RetryMiddleware.from_crawler(crawler)
    assert mw._max_retries == 7
    assert mw._backoff_base == 3.0
