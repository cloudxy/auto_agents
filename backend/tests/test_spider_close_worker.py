"""B2：多 worker 关闭回调不得互杀他人任务。"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRAPY_DIR = Path(__file__).resolve().parents[2] / "scrapy"
if str(SCRAPY_DIR) not in sys.path:
    sys.path.insert(0, str(SCRAPY_DIR))

from extensions import SpiderCloseWebhook  # noqa: E402


def _spider(name="example"):
    spider = MagicMock()
    spider.name = name
    spider.crawler.stats.get_value.return_value = 0
    return spider


def test_spider_closed_skips_when_local_empty_and_global_multi():
    ext = SpiderCloseWebhook("http://callback", "secret", "unused")
    client = MagicMock()
    client.smembers.side_effect = [set(), {"1", "2"}]
    ext._redis = client
    with patch.object(ext, "_callback_one") as cb:
        ext.spider_closed(_spider(), "finished")
    cb.assert_not_called()


def test_spider_closed_uses_local_task_ids():
    ext = SpiderCloseWebhook("http://callback", "secret", "unused")
    spider = _spider()
    ext._local_tasks[id(spider)] = {42}
    with patch.object(ext, "_callback_one") as cb:
        ext.spider_closed(spider, "finished")
    cb.assert_called_once()
    assert cb.call_args.args[0] == 42
