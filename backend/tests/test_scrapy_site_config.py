"""站点配置接线单测（P1-5 openweather + P1-7 站点级下载延迟）

约定：scrapy 侧代码经 importlib 加载（B2 红线：backend 包内不允许行首
直接导入 scrapy，测试亦遵守）。from_crawler 用假 crawler 注入 SITE_CONFIG。
"""
import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

_SCRAPY_DIR = str(Path(__file__).resolve().parents[2] / "scrapy")
if _SCRAPY_DIR not in sys.path:
    sys.path.insert(0, _SCRAPY_DIR)
os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "settings")


def _crawler_with_sites(sites: dict):
    crawler = MagicMock()
    crawler.settings.get.side_effect = lambda key, default=None: (
        {"sites": sites} if key == "SITE_CONFIG" else default
    )
    return crawler


# ---------------- P1-7：站点级 download_delay 生效 ----------------
def test_site_download_delay_applied_via_from_crawler():
    base_mod = importlib.import_module("spiders.base")

    class _Zhihu(base_mod.TaskAwareRedisSpider):
        name = "zhihu_feed"

    crawler = _crawler_with_sites({
        "zhihu_feed": {"anti_crawl": {"fixed_ua": True, "download_delay": 3}},
    })
    spider = _Zhihu.from_crawler(crawler)
    assert spider.download_delay == 3.0


def test_site_without_config_keeps_global_delay():
    base_mod = importlib.import_module("spiders.base")

    class _Plain(base_mod.TaskAwareRedisSpider):
        name = "generic"

    crawler = _crawler_with_sites({"zhihu_feed": {"anti_crawl": {"download_delay": 3}}})
    spider = _Plain.from_crawler(crawler)
    # 无站点配置：不设置 spider 属性，下载延迟由全局 DOWNLOAD_DELAY 提供
    assert not hasattr(spider, "download_delay")


def test_login_required_site_logs_warning_but_starts():
    base_mod = importlib.import_module("spiders.base")

    class _Dianping(base_mod.TaskAwareRedisSpider):
        name = "dianping_home"

    crawler = _crawler_with_sites({
        "dianping_home": {"login_required": True, "anti_crawl": {"download_delay": 4}},
    })
    spider = _Dianping.from_crawler(crawler)
    assert spider.download_delay == 4.0  # 告警不阻断启动


# ---------------- P1-5：openweather 修复 ----------------
def test_strip_appid_removes_key_but_keeps_other_params():
    ow = importlib.import_module("spiders.openweather")
    sanitized = ow.strip_appid(
        "https://api.openweathermap.org/data/2.5/weather?q=Beijing&appid=SECRET&units=metric"
    )
    assert "appid" not in sanitized
    assert "q=Beijing" in sanitized and "units=metric" in sanitized


def test_openweather_rejects_placeholder_key_and_injects_real_key():
    ow = importlib.import_module("spiders.openweather")
    spider = ow.OpenWeatherSpider(name="openweather")

    # 占位符/空 key：条目被明确丢弃（不再拿占位符发请求）
    spider.api_key = "YOUR_API_KEY_HERE"
    assert spider.make_request_from_data("https://api.openweathermap.org/data/2.5/weather?q=Beijing") is None
    spider.api_key = ""
    assert spider.make_request_from_data("https://api.openweathermap.org/data/2.5/weather?q=Beijing") is None

    # 真实 key：URL 缺 appid 时自动注入，并携带 task_id 归属
    spider.api_key = "real-key"
    req = spider.make_request_from_data(
        '{"url": "https://api.openweathermap.org/data/2.5/weather?q=Beijing", "task_id": 7}'
    )
    assert req is not None
    assert "appid=real-key" in req.url
    assert req.meta.get("task_id") == 7

    # URL 已带 appid：不重复注入
    req2 = spider.make_request_from_data(
        '{"url": "https://api.openweathermap.org/data/2.5/weather?q=SZ&appid=mine", "task_id": 8}'
    )
    assert req2.url.count("appid=") == 1


def test_openweather_item_url_sanitized():
    ow = importlib.import_module("spiders.openweather")

    class _Resp:
        url = "https://api.openweathermap.org/data/2.5/weather?q=BJ&appid=SECRET"
        status_code = 200

        @staticmethod
        def json():
            return {
                "name": "Beijing",
                "main": {"temp": 25, "humidity": 40},
                "weather": [{"description": "晴"}],
                "wind": {"speed": 3},
            }

    spider = ow.OpenWeatherSpider(name="openweather")
    items = list(spider.parse_weather(_Resp()))
    assert len(items) == 1
    # API Key 不入库：item.url 不含 appid
    assert "appid" not in items[0]["url"]
    assert items[0]["city"] == "Beijing"
