"""StorePipeline 重投与熔停单测（P1-4：推送失败不再静默丢数据）

约定：不连真实 Redis——rpush 用可注入的假客户端；scrapy 侧代码经
importlib 加载（B2 红线：backend 包内不允许行首 import scrapy）。
"""
import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SCRAPY_DIR = str(Path(__file__).resolve().parents[2] / "scrapy")
if _SCRAPY_DIR not in sys.path:
    sys.path.insert(0, _SCRAPY_DIR)
os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "settings")


def _load_pipelines():
    return importlib.import_module("pipelines")


class _FailingRedis:
    """rpush 恒失败的假客户端（模拟 Redis 不可达）"""

    def rpush(self, *args):
        raise ConnectionError("redis unreachable")


class _OKRedis:
    def __init__(self):
        self.pushed: list[str] = []

    def rpush(self, key, message):
        self.pushed.append(message)
        return 1


def _item_dict():
    # 构造最小可序列化 item 形态（Clean/Validate 已在管道链上游，这里直测 Store）
    return {"url": "https://example.com/a", "title": "t", "content": "c", "source": "s"}


def _pipeline(pipelines_mod, redis_client):
    pipeline = pipelines_mod.StorePipeline()
    pipeline.redis = redis_client
    pipeline._consecutive_failures = 0
    return pipeline


# patch time.sleep 避免退避拖慢测试
@pytest.fixture(autouse=True)
def _no_sleep():
    with patch.object(importlib.import_module("time"), "sleep", lambda s: None):
        yield


def test_push_failure_retries_then_drops_and_counts():
    pipelines = _load_pipelines()
    pipeline = _pipeline(pipelines, _FailingRedis())
    spider = MagicMock(name="ow")
    spider.name = "spider_x"

    # 单条重投 3 次后丢弃（不抛），连续失败计数 +1
    pipeline.process_item(_item_dict(), spider)
    assert pipeline._consecutive_failures == 1


def test_consecutive_failures_stop_spider():
    """连续 _MAX_CONSECUTIVE_FAILURES 条重投耗尽 → CloseSpider 停止采集"""
    pipelines = _load_pipelines()
    pipeline = _pipeline(pipelines, _FailingRedis())
    spider = MagicMock(name="ow")
    spider.name = "spider_x"

    from scrapy.exceptions import CloseSpider

    with pytest.raises(CloseSpider):
        for _ in range(pipelines.StorePipeline._MAX_CONSECUTIVE_FAILURES):
            pipeline.process_item(_item_dict(), spider)


def test_success_resets_consecutive_failure_counter():
    pipelines = _load_pipelines()
    ok = _OKRedis()
    pipeline = _pipeline(pipelines, ok)
    spider = MagicMock(name="ow")
    spider.name = "spider_x"

    pipeline._consecutive_failures = pipeline._MAX_CONSECUTIVE_FAILURES - 1
    pipeline.process_item(_item_dict(), spider)
    assert pipeline._consecutive_failures == 0  # 成功即复位，不会误停
    assert len(ok.pushed) == 1
    import json

    msg = json.loads(ok.pushed[0])
    assert msg["spider_name"] == "spider_x" and msg["item"]["url"].startswith("https://")
