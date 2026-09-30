"""质量分口径 v2（审计 BUG-21 / F4 QA-2 回归）：用真实 QualityCheckPipeline，不 mock 分数"""
import importlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

_SCRAPY_DIR = str(Path(__file__).resolve().parents[2] / "scrapy")
if _SCRAPY_DIR not in sys.path:
    sys.path.insert(0, _SCRAPY_DIR)
os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "settings")


def _pipe():
    mod = importlib.import_module("pipelines.quality")
    spider = MagicMock()
    spider.settings.getlist.side_effect = lambda k, d=None: d
    spider.settings.getbool.side_effect = lambda k, d=None: d
    p = mod.QualityCheckPipeline()
    p.open_spider(spider)
    return p


def _flow_item(fields: dict, url="https://shop.example/list", title=None):
    items = importlib.import_module("items")
    it = items.BaseItem()
    it["url"] = url
    it["title"] = title or (fields.get("title") or [url])[0]
    it["content"] = json.dumps(fields, ensure_ascii=False)
    it["source"] = "flow"
    it["task_id"] = 9
    return it


def test_only_title_hit_scores_below_trial_gate():
    """声明 3 个选择器只命中 title → < 40（原口径恒 ≥ 50，试采闸失效）"""
    item = _pipe().process_item(_flow_item({"title": ["商品A"], "price": [], "desc": []}), None)
    assert item["_quality_score"] < 40


def test_all_selectors_hit_scores_full():
    item = _pipe().process_item(_flow_item({"title": ["A"], "price": ["¥9"], "desc": ["好"]}), None)
    assert item["_quality_score"] == 100.0


def test_value_equal_to_url_is_not_valid():
    url = "https://shop.example/list"
    item = _pipe().process_item(_flow_item({"title": [url], "price": ["¥9"]}, url=url), None)
    assert item["_quality_score"] == 50.0  # 命中 2/2，但 title 只是 URL，有效 1/2


def test_duplicate_is_penalized():
    p = _pipe()
    first = p.process_item(_flow_item({"title": ["A"], "price": ["1"]}), None)["_quality_score"]
    second = p.process_item(_flow_item({"title": ["A"], "price": ["1"]}), None)["_quality_score"]
    assert first == 100.0 and second == 60.0


def test_non_selector_item_ignores_internal_fields():
    items = importlib.import_module("items")
    it = items.BaseItem()
    it["url"] = "https://a.example/1"
    it["title"] = "https://a.example/1"  # 标题回退成 URL = 缺失
    it["content"] = "正文"
    it["task_id"] = 1
    score = _pipe().process_item(it, None)["_quality_score"]
    assert 0 < score < 100
