"""阶段 3 单测 - 3.1 通用爬虫配置化采集

覆盖：
- extract_selectors 参数解析
- 消费者分发时带选择器的 URL 包装为 JSON 条目
- generic 爬虫选择器提取（css/xpath/regex、非法规则跳过、无字段丢弃）
- 注册表含 custom 类型与 generic 爬虫

约定：与前两阶段一致不连真实 MySQL/Redis；scrapy 侧代码经 importlib 加载
（B2 红线：backend 包内不允许行首 `import scrapy`，测试亦遵守）。
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tasks.consumer import SpiderTaskConsumer, extract_selectors

# scrapy 项目根加入路径（与 run_spider.py 相同的加载方式）
_SCRAPY_DIR = str(Path(__file__).resolve().parents[2] / "scrapy")
if _SCRAPY_DIR not in sys.path:
    sys.path.insert(0, _SCRAPY_DIR)
os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "settings")


def _load_generic_spider():
    """经 importlib 加载 generic 爬虫（避免行首 import scrapy 触发 B2 检查）"""
    import importlib

    module = importlib.import_module("spiders.generic")
    return module.GenericSpider


# ---------------- extract_selectors ----------------
def test_extract_selectors_valid():
    params = json.dumps({
        "urls": ["https://example.com"],
        "selectors": [{"name": "title", "type": "css", "expr": "h1::text"}],
    })
    selectors = extract_selectors(params)
    assert selectors == [{"name": "title", "type": "css", "expr": "h1::text"}]


def test_extract_selectors_absent_or_invalid():
    assert extract_selectors(None) == []
    assert extract_selectors('{"urls": ["https://a.com"]}') == []
    assert extract_selectors("not-json") == []
    # 非 dict 元素被过滤
    params = json.dumps({"selectors": [{"name": "t"}, "bad", 3]})
    assert extract_selectors(params) == [{"name": "t"}]


# ---------------- 消费者分发包装 ----------------
def _dispatch_stubs():
    """构造 _dispatch 的 session/repo 桩（AsyncSession + SpiderTaskRepository 均被 patch）"""
    session = MagicMock()
    session.commit = AsyncMock()
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    repo = MagicMock()
    repo.update = AsyncMock(return_value=MagicMock())
    repo.get_by_id = AsyncMock(return_value=MagicMock())  # 任务仍存在
    return session_cm, repo


@pytest.mark.asyncio
async def test_dispatch_wraps_urls_with_selectors():
    """params 带 selectors 时，投递到 start_urls 队列的是 {url, selectors} JSON 条目"""
    consumer = SpiderTaskConsumer()
    consumer._redis = AsyncMock()
    consumer._engine = MagicMock()
    consumer._record_log_offset = AsyncMock()

    session_cm, repo = _dispatch_stubs()
    msg = {
        "task_id": 1,
        "spider_name": "generic",
        "params": json.dumps({
            "urls": ["https://example.com"],
            "selectors": [{"name": "title", "type": "css", "expr": "h1::text"}],
        }),
    }
    with patch("backend.tasks.consumer.AsyncSession", return_value=session_cm), \
         patch("backend.tasks.consumer.SpiderTaskRepository", return_value=repo):
        await consumer._dispatch(msg)

    consumer._redis.rpush.assert_awaited_once()
    key, payload = consumer._redis.rpush.await_args.args
    assert key == "generic:start_urls"
    entry = json.loads(payload)
    assert entry["url"] == "https://example.com"
    assert entry["selectors"][0]["expr"] == "h1::text"


@pytest.mark.asyncio
async def test_dispatch_plain_urls_without_selectors():
    """普通类型任务载荷不带 selectors（阶段 4.1 起统一 JSON 包装并携带 task_id）"""
    consumer = SpiderTaskConsumer()
    consumer._redis = AsyncMock()
    consumer._engine = MagicMock()
    consumer._record_log_offset = AsyncMock()

    session_cm, repo = _dispatch_stubs()
    msg = {
        "task_id": 2,
        "spider_name": "example",
        "params": json.dumps({"urls": ["https://example.com"]}),
    }
    with patch("backend.tasks.consumer.AsyncSession", return_value=session_cm), \
         patch("backend.tasks.consumer.SpiderTaskRepository", return_value=repo):
        await consumer._dispatch(msg)

    key, payload = consumer._redis.rpush.await_args.args
    assert key == "example:start_urls"
    entry = json.loads(payload)
    assert entry["url"] == "https://example.com"
    assert entry["task_id"] == 2  # 结果归属走请求 meta（阶段 4.1）
    assert "selectors" not in entry


# ---------------- generic 爬虫提取 ----------------
def _response(body: str):
    import importlib

    scrapy_http = importlib.import_module("scrapy.http")
    scrapy_req = importlib.import_module("scrapy")
    request = scrapy_req.Request("https://example.com")
    return scrapy_http.HtmlResponse(
        url="https://example.com", body=body.encode("utf-8"),
        encoding="utf-8", request=request,
    )


_PAGE = (
    "<html><head><title>页面标题</title></head>"
    "<body><h1>Hello</h1><p>a</p><p>b</p><span class=\"tag\">v1.2.3</span></body></html>"
)


def test_generic_parse_css_xpath_regex():
    GenericSpider = _load_generic_spider()
    spider = GenericSpider()
    response = _response(_PAGE)
    response.meta["selectors"] = [
        {"name": "title", "type": "css", "expr": "title::text"},
        {"name": "paragraphs", "type": "xpath", "expr": "//p/text()"},
        {"name": "version", "type": "regex", "expr": r"v\d+\.\d+\.\d+"},
    ]

    items = list(spider.parse(response))
    assert len(items) == 1
    item = items[0]
    assert item["title"] == "页面标题"
    assert item["source"] == "custom"
    fields = json.loads(item["content"])
    assert fields["title"] == ["页面标题"]
    assert fields["paragraphs"] == ["a", "b"]
    assert fields["version"] == ["v1.2.3"]


def test_generic_parse_skips_invalid_rule():
    GenericSpider = _load_generic_spider()
    spider = GenericSpider()
    response = _response(_PAGE)
    response.meta["selectors"] = [
        {"name": "", "type": "css", "expr": "h1::text"},       # 无字段名
        {"name": "x", "type": "unknown", "expr": "h1"},        # 非法类型
        {"name": "heading", "type": "css", "expr": "h1::text"},
    ]
    items = list(spider.parse(response))
    fields = json.loads(items[0]["content"])
    assert set(fields.keys()) == {"heading"}
    assert fields["heading"] == ["Hello"]


def test_generic_parse_drops_when_no_fields():
    from scrapy.exceptions import DropItem

    GenericSpider = _load_generic_spider()
    spider = GenericSpider()
    response = _response(_PAGE)
    response.meta["selectors"] = []
    with pytest.raises(DropItem):
        list(spider.parse(response))


def test_generic_make_request_from_data():
    GenericSpider = _load_generic_spider()
    spider = GenericSpider()
    entry = json.dumps({
        "url": "https://example.com",
        "selectors": [{"name": "t", "type": "css", "expr": "h1::text"}],
    })
    request = spider.make_request_from_data(entry)
    assert request.url == "https://example.com"
    assert request.meta["selectors"][0]["name"] == "t"
    # 纯 URL 兜底
    plain = spider.make_request_from_data("https://plain.example.com")
    assert plain.meta["selectors"] == []


# ---------------- 代理池中间件（3.2） ----------------
def _load_proxy_middleware():
    import importlib

    module = importlib.import_module("middlewares")
    return module.ProxyMiddleware


def _request(url="https://example.com"):
    import importlib

    scrapy_mod = importlib.import_module("scrapy")
    return scrapy_mod.Request(url)


def test_proxy_disabled_passes_through():
    ProxyMiddleware = _load_proxy_middleware()
    mw = ProxyMiddleware(enabled=False, proxy_list=["http://p1:8080"])
    request = _request()
    assert mw.process_request(request, None) is None
    assert "proxy" not in request.meta


def test_proxy_static_pool_rotation():
    ProxyMiddleware = _load_proxy_middleware()
    mw = ProxyMiddleware(enabled=True, proxy_list=["http://p1:8080", "http://p2:8080"])
    request = _request()
    mw.process_request(request, None)
    assert request.meta["proxy"] in {"http://p1:8080", "http://p2:8080"}


def test_proxy_failed_removed_then_direct():
    """B3 评分机制：从未成功的代理一次失败即剔除（score=0.0 < 阈值 0.2）"""
    ProxyMiddleware = _load_proxy_middleware()
    mw = ProxyMiddleware(enabled=True, proxy_list=["http://only:8080"])

    # Mock Redis 以支持评分存储/读取（区分 scores 和 stats 两个 HASH）
    fake_redis = MagicMock()
    scores_data: dict = {}   # spider:proxy:scores
    stats_data: dict = {}    # spider:proxy:stats

    def mock_hget(key, field):
        if "scores" in key:
            return scores_data.get(field)
        return stats_data.get(field)

    def mock_hset(key, field, val):
        if "scores" in key:
            scores_data[field] = val
        else:
            stats_data[field] = val

    fake_redis.hgetall.return_value = {}
    fake_redis.hget.side_effect = mock_hget
    fake_redis.hset.side_effect = mock_hset
    mw._redis_client = fake_redis

    request = _request()
    mw.process_request(request, None)
    assert request.meta["proxy"] == "http://only:8080"

    # 从未成功的代理一次失败后 score=0.0 < 阈值 0.2，被剔除
    mw.process_exception(request, ConnectionError("refused"), None)
    assert mw.failed_proxies == {"http://only:8080"}

    # 池空后直连（不再写 meta）
    request2 = _request()
    assert mw.process_request(request2, None) is None
    assert "proxy" not in request2.meta


def test_proxy_redis_pool_priority(monkeypatch):
    ProxyMiddleware = _load_proxy_middleware()
    mw = ProxyMiddleware(
        enabled=True,
        proxy_list=["http://static:8080"],
        redis_key="spider:proxy_pool",
        redis_url="redis://${MOCK_REDIS}",  # Redis 客户端已被 mock，仅验证参数透传
    )
    fake_client = MagicMock()
    fake_client.lrange.return_value = ["http://dynamic:8080", ""]
    fake_redis_mod = MagicMock()
    fake_redis_mod.Redis.from_url.return_value = fake_client
    monkeypatch.setitem(sys.modules, "redis", fake_redis_mod)

    request = _request()
    mw.process_request(request, None)
    assert request.meta["proxy"] == "http://dynamic:8080"  # Redis 池优先于静态列表
    fake_client.lrange.assert_called_once_with("spider:proxy_pool", 0, -1)


# ---------------- 注册表迁库（3.3） ----------------
@pytest.mark.asyncio
async def test_registry_db_first():
    """spider_definitions 有数据时清单来自 DB（非配置）"""
    from types import SimpleNamespace

    from backend.services.spider_service import SpiderService

    svc = SpiderService.__new__(SpiderService)
    svc.session = MagicMock()
    definition = SimpleNamespace(
        name="db_only_spider", title="仅存于 DB", type="web", description="db"
    )
    with patch("backend.services.spider_service.SpiderDefinitionRepository") as repo_cls:
        repo_cls.return_value.list_enabled = AsyncMock(return_value=[definition])
        resp = await svc.registry()

    assert [s.name for s in resp.spiders] == ["db_only_spider"]  # 未回退配置
    assert resp.types  # 类型表单仍来自配置（含 custom）


@pytest.mark.asyncio
async def test_registry_fallback_to_config_on_db_error():
    """DB 异常时清单回退配置种子"""
    from backend.services.spider_service import SpiderService

    svc = SpiderService.__new__(SpiderService)
    svc.session = MagicMock()
    with patch("backend.services.spider_service.SpiderDefinitionRepository") as repo_cls:
        repo_cls.return_value.list_enabled = AsyncMock(side_effect=RuntimeError("db down"))
        resp = await svc.registry()

    names = {s.name for s in resp.spiders}
    assert "example" in names and "generic" in names  # 配置种子兜底


def test_registry_contains_custom_type_and_generic(client):
    """注册表端点含 custom 类型与 generic 爬虫（DB 种子或配置兜底均可）"""
    body = client.get("/api/v1/spiders/registry").json()
    type_map = {t["type"]: t for t in body["types"]}
    assert "custom" in type_map
    selector_field = next(
        f for f in type_map["custom"]["fields"] if f["name"] == "selectors"
    )
    assert selector_field["kind"] == "selectors"
    assert selector_field["required"] is True

    spider_map = {s["name"]: s for s in body["spiders"]}
    assert spider_map["generic"]["type"] == "custom"
