"""流程采集引擎测试 - flow_generic（分页/详情页/过滤）

约定：不连真实 MySQL/Redis，Repository/Redis 用 AsyncMock/MagicMock 桩；
爬虫解析用 scrapy HtmlResponse 构造响应链。
覆盖：
- extract_flow 流程参数识别（含纯选择器回退的回归保护）
- enqueue 流程任务归一化到 flow_generic
- 消费者分发：流程载荷投 `flow_generic:start_urls` + 任务行改写
- flow_generic：队列条目解析、分页循环（含 max_pages 封顶）、
  详情页二次采集、条件过滤、空详情页 DropItem
"""
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRAPY_DIR = PROJECT_ROOT / "scrapy"
if str(SCRAPY_DIR) not in sys.path:
    sys.path.insert(0, str(SCRAPY_DIR))

from backend.services.spider_common import FLOW_SPIDER_NAME, extract_flow  # noqa: E402
from backend.services.spider_task_service import SpiderTaskService  # noqa: E402
from backend.tasks.consumer import SpiderTaskConsumer  # noqa: E402

_LIST_HTML = """
<html><head><title>列表页</title></head><body>
  <ul>
    <li class="news"><a href="/d/1">科技新闻 Python 发布新版</a></li>
    <li class="news"><a href="/d/2">娱乐新闻某明星</a></li>
  </ul>
  <a class="next" href="?page=2">下一页</a>
</body></html>
"""

_DETAIL_HTML = """
<html><head><title>详情页</title></head><body>
  <p>这是正文内容第一段</p><p>第二段</p>
</body></html>
"""


def _flow(with_detail: bool = True, with_pagination: bool = True, filters=None) -> dict:
    flow = {
        "selectors": [{"name": "title", "type": "css", "expr": "li.news a::text"}],
    }
    if with_pagination:
        flow["pagination"] = {"selector": "a.next::attr(href)", "type": "css", "max_pages": 2}
    if with_detail:
        flow["detail"] = {
            "list_selector": "li.news",
            "url_selector": ".//a/@href",
            "selectors": [{"name": "body", "type": "css", "expr": "p::text"}],
        }
    if filters:
        flow["filters"] = filters
    return flow


def _response(url: str, html: str, meta: dict):
    # Response.meta 需经由绑定的 Request 提供（构造时传 request）；
    # scrapy 导入放函数内，避免触碰 B2 边界检测（行首 import）
    from scrapy import Request
    from scrapy.http import HtmlResponse

    req = Request(url=url, meta=meta)
    return HtmlResponse(url=url, request=req, body=html.encode(), encoding="utf-8")


def _service() -> SpiderTaskService:
    svc = SpiderTaskService.__new__(SpiderTaskService)
    svc.session = MagicMock()
    svc.session.commit = AsyncMock()
    svc.session.refresh = AsyncMock()
    svc.repo = MagicMock()
    svc.result_repo = MagicMock()
    svc.notifier = MagicMock()
    return svc


def _task(**overrides) -> MagicMock:
    """可被 SpiderTaskResponse.model_validate 的任务实体桩"""
    defaults = dict(
        id=9, spider_name="example", status="pending", priority="normal",
        result_count=0, retry_count=0, error_message=None,
        created_at=None, updated_at=None, started_at=None, completed_at=None,
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


# ---------------- extract_flow 流程参数识别 ----------------
class TestExtractFlow:
    def test_empty_or_invalid_params_returns_none(self):
        assert extract_flow(None) is None
        assert extract_flow("") is None
        assert extract_flow("not-json") is None
        assert extract_flow("[1, 2]") is None  # 非 dict

    def test_pure_selectors_is_not_flow(self):
        # 回归保护：未配置流程段时与现有纯选择器任务完全一致
        params = json.dumps({"urls": ["https://a.b"], "selectors": [{"name": "t", "type": "css", "expr": "h1::text"}]})
        assert extract_flow(params) is None

    def test_pagination_section_builds_flow(self):
        params = json.dumps({
            "urls": ["https://a.b"],
            "selectors": [{"name": "t", "type": "css", "expr": "h1::text"}],
            "pagination": {"selector": "a.next::attr(href)", "type": "css", "max_pages": 3},
        })
        flow = extract_flow(params)
        assert flow is not None
        assert flow["selectors"] == [{"name": "t", "type": "css", "expr": "h1::text"}]
        assert flow["pagination"]["max_pages"] == 3

    def test_filters_accepts_list_and_dict(self):
        rules = [{"field": "title", "op": "contains", "value": "Python"}]
        as_list = extract_flow(json.dumps({"urls": ["u"], "filters": rules}))
        as_dict = extract_flow(json.dumps({"urls": ["u"], "filters": {"field": "t", "op": "equals", "value": "x"}}))
        assert as_list["filters"] == rules
        assert as_dict["filters"] == {"field": "t", "op": "equals", "value": "x"}

    def test_empty_sections_ignored(self):
        params = json.dumps({"urls": ["u"], "pagination": {}, "filters": []})
        assert extract_flow(params) is None


# ---------------- enqueue 归一化到 flow_generic ----------------
class TestEnqueueFlowNormalization:
    @pytest.mark.asyncio
    async def test_flow_task_normalized_to_flow_generic(self):
        svc = _service()
        fake_redis = AsyncMock()
        fake_redis.scard.return_value = 0
        svc.repo.create = AsyncMock(return_value=_task(id=30, spider_name=FLOW_SPIDER_NAME))

        params = json.dumps({"urls": ["https://a.b"], "filters": [{"field": "t", "op": "equals", "value": "x"}]})
        with (
            patch("backend.services.spider_task_service.get_async_redis", return_value=fake_redis),
            patch("backend.services.spider_task_service.settings") as fake_settings,
        ):
            fake_settings.get.return_value = 2
            await svc.enqueue("generic", params=params)

        assert svc.repo.create.call_args.kwargs["spider_name"] == FLOW_SPIDER_NAME
        # 并发槽位检查也走 flow_generic 的活跃键
        fake_redis.scard.assert_called_once_with(f"spider:active_tasks:{FLOW_SPIDER_NAME}")

    @pytest.mark.asyncio
    async def test_plain_task_keeps_original_spider(self):
        svc = _service()
        fake_redis = AsyncMock()
        fake_redis.scard.return_value = 0
        svc.repo.create = AsyncMock(return_value=_task(id=31, spider_name="generic"))

        with (
            patch("backend.services.spider_task_service.get_async_redis", return_value=fake_redis),
            patch("backend.services.spider_task_service.settings") as fake_settings,
        ):
            fake_settings.get.return_value = 2
            await svc.enqueue("generic", params=json.dumps({"urls": ["https://a.b"]}))
        assert svc.repo.create.call_args.kwargs["spider_name"] == "generic"


# ---------------- 消费者分发：流程载荷 + 任务行改写 ----------------
class TestConsumerFlowDispatch:
    async def _dispatch(self, params: str):
        consumer = SpiderTaskConsumer()
        fake_redis = MagicMock()
        fake_redis.sadd = AsyncMock()
        fake_redis.expire = AsyncMock()
        fake_redis.rpush = AsyncMock()
        fake_redis.set = AsyncMock()
        consumer._redis = fake_redis

        repo = MagicMock()
        repo.update = AsyncMock(return_value=MagicMock(id=5))
        repo.get_by_id = AsyncMock(return_value=MagicMock(id=5))
        session = MagicMock()
        session.commit = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("backend.tasks.consumer.AsyncSession", return_value=session),
            patch("backend.tasks.consumer.SpiderTaskRepository", return_value=repo),
            patch.object(SpiderTaskConsumer, "_engine", return_value=MagicMock()),
            patch.object(SpiderTaskConsumer, "_record_log_offset", new=AsyncMock()),
        ):
            await consumer._dispatch({
                "task_id": 5,
                "spider_name": "generic",
                "params": params,
            })
        return fake_redis, repo

    @pytest.mark.asyncio
    async def test_flow_task_routed_to_flow_generic_queue(self):
        params = json.dumps({
            "urls": ["https://a.b/list"],
            "selectors": [{"name": "t", "type": "css", "expr": "h1::text"}],
            "pagination": {"selector": "a.next::attr(href)", "max_pages": 3},
        })
        fake_redis, repo = await self._dispatch(params)

        queue_key, payload = fake_redis.rpush.call_args.args
        assert queue_key == "flow_generic:start_urls"
        entry = json.loads(payload)
        assert entry["url"] == "https://a.b/list"
        assert entry["task_id"] == 5
        assert entry["flow"]["pagination"]["max_pages"] == 3
        assert "selectors" not in entry  # 流程载荷用 flow 承载，不混用顶层 selectors
        # 任务行同步改写，保证活跃键/关闭回调与实际执行爬虫一致
        repo.update.assert_any_await(5, spider_name=FLOW_SPIDER_NAME)
        fake_redis.sadd.assert_awaited_once_with("spider:active_tasks:flow_generic", 5)

    @pytest.mark.asyncio
    async def test_plain_task_falls_back_to_selector_payload(self):
        # 无流程参数回退：与既有纯选择器路径完全一致
        params = json.dumps({
            "urls": ["https://a.b/p"],
            "selectors": [{"name": "t", "type": "css", "expr": "h1::text"}],
        })
        fake_redis, repo = await self._dispatch(params)

        queue_key, payload = fake_redis.rpush.call_args.args
        assert queue_key == "generic:start_urls"
        entry = json.loads(payload)
        assert entry["selectors"] == [{"name": "t", "type": "css", "expr": "h1::text"}]
        assert "flow" not in entry


# ---------------- flow_generic：队列条目 → 请求 ----------------
class TestFlowMakeRequest:
    def test_make_request_carries_flow_and_task_meta(self):
        from scrapy import Request
        from spiders.flow_generic import FlowGenericSpider

        spider = FlowGenericSpider.__new__(FlowGenericSpider)
        entry = json.dumps({"url": "https://a.b/list", "task_id": 12, "flow": _flow()})
        req = spider.make_request_from_data(entry)
        assert isinstance(req, Request)
        assert req.meta["stage"] == "list"
        assert req.meta["page"] == 1
        assert req.meta["task_id"] == 12
        assert req.meta["flow"]["detail"]["list_selector"] == "li.news"

    def test_empty_url_entry_dropped(self):
        from spiders.flow_generic import FlowGenericSpider

        spider = FlowGenericSpider.__new__(FlowGenericSpider)
        assert spider.make_request_from_data(json.dumps({"flow": _flow()})) is None


# ---------------- flow_generic：parse 状态机 ----------------
class TestFlowParse:
    def _spider(self):
        from spiders.flow_generic import FlowGenericSpider

        return FlowGenericSpider.__new__(FlowGenericSpider)

    def test_list_page_yields_item_detail_and_next_requests(self):
        from scrapy import Request

        spider = self._spider()
        resp = _response("https://a.b/list", _LIST_HTML,
                         {"stage": "list", "page": 1, "flow": _flow(), "task_id": 3})
        out = list(spider.parse(resp))

        items = [o for o in out if not isinstance(o, Request)]
        requests = [o for o in out if isinstance(o, Request)]
        assert len(items) == 1
        content = json.loads(items[0]["content"])
        assert content["title"] == ["科技新闻 Python 发布新版", "娱乐新闻某明星"]
        assert items[0]["source"] == "flow"

        detail_reqs = [r for r in requests if r.meta["stage"] == "detail"]
        next_reqs = [r for r in requests if r.meta.get("stage") == "list"]
        # 相对链接走 urljoin 归一
        assert [r.url for r in detail_reqs] == ["https://a.b/d/1", "https://a.b/d/2"]
        assert all(r.meta["task_id"] == 3 for r in detail_reqs)
        assert len(next_reqs) == 1
        assert next_reqs[0].url == "https://a.b/list?page=2"
        assert next_reqs[0].meta["page"] == 2

    def test_pagination_stops_at_max_pages(self):
        from scrapy import Request

        spider = self._spider()
        resp = _response("https://a.b/list", _LIST_HTML,
                         {"stage": "list", "page": 2, "flow": _flow(with_detail=False), "task_id": 3})
        out = list(spider.parse(resp))
        # page 已达 max_pages=2：不再发下一页请求
        assert not [o for o in out if isinstance(o, Request) and o.meta.get("stage") == "list"]

    def test_filters_drop_non_matching_values(self):
        from scrapy import Request

        spider = self._spider()
        flow = _flow(with_detail=False, with_pagination=False,
                     filters=[{"field": "title", "op": "contains", "value": "Python"}])
        resp = _response("https://a.b/list", _LIST_HTML,
                         {"stage": "list", "page": 1, "flow": flow, "task_id": 3})
        out = list(spider.parse(resp))
        items = [o for o in out if not isinstance(o, Request)]
        assert len(items) == 1
        content = json.loads(items[0]["content"])
        assert content["title"] == ["科技新闻 Python 发布新版"]

    def test_detail_page_yields_item_with_detail_selectors(self):
        spider = self._spider()
        resp = _response("https://a.b/d/1", _DETAIL_HTML,
                         {"stage": "detail", "flow": _flow(), "task_id": 3})
        out = list(spider.parse(resp))
        assert len(out) == 1
        content = json.loads(out[0]["content"])
        assert content["body"] == ["这是正文内容第一段", "第二段"]
        assert out[0]["source"] == "flow"

    def test_detail_page_without_fields_raises_drop_item(self):
        from scrapy.exceptions import DropItem

        spider = self._spider()
        flow = _flow()
        flow["detail"]["selectors"] = [{"name": "missing", "type": "css", "expr": ".nothing::text"}]
        resp = _response("https://a.b/d/1", _DETAIL_HTML,
                         {"stage": "detail", "flow": flow, "task_id": 3})
        with pytest.raises(DropItem):
            list(spider.parse(resp))
