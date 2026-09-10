"""任务消费者纯函数单测 - params 中 start URL 的提取约定 + M4 flow 渲染参数透传契约

不连真实 Redis/MySQL：只测纯函数解析分支。
M4 跨层契约：flow 任务 params 含 render_js/wait_for/wait_timeout 时，
start_urls 载荷必须携带 params（flow_generic 从 extra["params"] 读取）；
非 flow 任务载荷结构零变化。
"""
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.spider_common import extract_flow  # noqa: E402
from backend.tasks.consumer import (  # noqa: E402
    build_start_payload,
    extract_render_params,
    extract_selectors,
    extract_start_urls,
)


def test_dict_with_urls():
    params = json.dumps({"urls": ["https://example.com/1", "https://example.com/2"]})
    assert extract_start_urls(params) == ["https://example.com/1", "https://example.com/2"]


def test_dict_without_urls_returns_empty():
    assert extract_start_urls(json.dumps({"foo": "bar"})) == []


def test_none_and_empty_return_empty():
    assert extract_start_urls(None) == []
    assert extract_start_urls("") == []


def test_invalid_json_returns_empty():
    assert extract_start_urls("not-json{") == []


def test_list_params_supported():
    assert extract_start_urls('["https://example.com"]') == ["https://example.com"]


def test_blank_urls_filtered():
    params = json.dumps({"urls": ["https://example.com", "", None]})
    assert extract_start_urls(params) == ["https://example.com"]


# ---------------- M4：flow 任务渲染参数透传契约 ----------------
_FLOW_TASK_PARAMS = {
    "urls": ["https://example.com/list"],
    "selectors": [{"name": "title", "type": "css", "expr": "h1"}],
    "pagination": {"selector": "a.next", "type": "css", "max_pages": 2},
    "render_js": True,
    "wait_for": "div.content",
    "wait_timeout": 30,
    "evil_key": "should-not-leak",
}


def test_flow_task_render_params_passthrough_contract():
    """M4 跨层契约：flow 任务 params 含 render_js → start_urls 载荷带 params.render_js=True

    对齐 flow_generic.make_request_from_data 的读取约定（extra["params"]）；
    白名单外的键（evil_key）不透传。"""
    params = json.dumps(_FLOW_TASK_PARAMS)
    flow = extract_flow(params)
    assert flow is not None  # 任务会被切到 flow_generic
    payload = json.loads(build_start_payload(
        "https://example.com/list", task_id=41, flow=flow,
        selectors=extract_selectors(params),
        render_params=extract_render_params(params),
    ))
    assert payload["params"]["render_js"] is True
    assert payload["params"]["wait_for"] == "div.content"
    assert payload["params"]["wait_timeout"] == 30
    assert "evil_key" not in payload["params"]
    assert payload["flow"]["pagination"]["max_pages"] == 2
    assert payload["task_id"] == 41
    assert payload["url"] == "https://example.com/list"


def test_render_params_strict_type_whitelist():
    """类型不合法的渲染参数不透传（防注入），合法的 float wait_timeout 归一为 int"""
    bad = extract_render_params(json.dumps({
        "render_js": "yes", "wait_for": 123, "wait_timeout": "30",
    }))
    assert bad == {}
    good = extract_render_params(json.dumps({
        "render_js": False, "wait_for": "h1", "wait_timeout": 15.0,
    }))
    assert good == {"render_js": False, "wait_for": "h1", "wait_timeout": 15}
    assert extract_render_params(None) == {}
    assert extract_render_params("not-json{") == {}


def test_flow_payload_without_render_params_has_no_params_key():
    """flow 任务无渲染参数时载荷不携带 params 键（结构最小变化）"""
    params = json.dumps({"urls": ["https://example.com/list"],
                         "pagination": {"selector": "a.next", "type": "css", "max_pages": 2}})
    payload = json.loads(build_start_payload(
        "https://example.com/list", task_id=7, flow=extract_flow(params),
        selectors=[], render_params=extract_render_params(params),
    ))
    assert "params" not in payload
    assert "flow" in payload


def test_non_flow_payload_unchanged():
    """M4 仅 flow 分支透传：非 flow 任务载荷结构零变化（无 params 键）"""
    payload = json.loads(build_start_payload(
        "https://example.com/1", task_id=7, flow=None,
        selectors=[{"name": "t", "type": "css", "expr": "h1"}], render_params=None,
    ))
    assert payload == {
        "url": "https://example.com/1", "task_id": 7,
        "selectors": [{"name": "t", "type": "css", "expr": "h1"}],
    }
    # flow=None 且无 selectors：与旧实现一致，仅 url + task_id
    payload = json.loads(build_start_payload(
        "https://example.com/1", task_id=8, flow=None, selectors=[], render_params={}))
    assert payload == {"url": "https://example.com/1", "task_id": 8}


# ---------------- T-07：回流归属=入队企业；无主不写「我的结果」 ----------------
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

from backend.tasks.consumer import SpiderTaskConsumer  # noqa: E402
from platform_core.queues import DEAD_ITEM_QUEUE  # noqa: E402


def _flush_session():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.add_all = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return session, ctx


@pytest.mark.asyncio
async def test_flush_result_tenant_is_task_owner_not_message():
    """GWT-10.1 / 10.2：工人消息不带企业（或带错企业）→ 结果归属=入队任务企业"""
    consumer = SpiderTaskConsumer()
    consumer._redis = AsyncMock()
    consumer._fail_task = AsyncMock()
    task = MagicMock(params=None, tenant_id=11)
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=task)
    repo.batch_increment_result_counts = AsyncMock()
    repo.find_by_content_hash = AsyncMock(return_value=None)
    session, ctx = _flush_session()
    qs = MagicMock()
    qs.check_result_storage = AsyncMock()

    msg = {
        "task_id": 7, "spider_name": "flow_generic",
        "item": {"url": "https://wiz.example", "title": "wiz"},
        "tenant_id": 99,
    }
    with patch("backend.tasks.consumer.AsyncSession", return_value=ctx), \
         patch("backend.tasks.consumer.SpiderTaskRepository", return_value=repo), \
         patch("backend.tasks.consumer.SpiderResultRepository", return_value=repo), \
         patch("backend.tasks.consumer.SpiderTaskConsumer._engine",
               staticmethod(lambda: object())), \
         patch("backend.services.quota_service.QuotaService", return_value=qs):
        await consumer._flush_batch([msg], {7: 1})

    session.add_all.assert_called_once()
    written = session.add_all.call_args.args[0]
    assert len(written) == 1
    assert written[0].tenant_id == 11
    assert written[0].task_id == 7
    consumer._fail_task.assert_not_awaited()
    consumer._redis.rpush.assert_not_awaited()


@pytest.mark.asyncio
async def test_flush_orphan_not_written_dead_letter_and_fail_task():
    """GWT-10.4：回流找不到入队企业 → 不写「我的结果」；死信 + 任务失败；不丢给别的企业"""
    consumer = SpiderTaskConsumer()
    consumer._redis = AsyncMock()
    consumer._fail_task = AsyncMock()
    task = MagicMock(params=None, tenant_id=None)
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=task)
    repo.batch_increment_result_counts = AsyncMock()
    session, ctx = _flush_session()

    msg = {
        "task_id": 8, "spider_name": "s1",
        "item": {"url": "https://orphan.example", "title": "no-owner"},
        "tenant_id": 3,
    }
    with patch("backend.tasks.consumer.AsyncSession", return_value=ctx), \
         patch("backend.tasks.consumer.SpiderTaskRepository", return_value=repo), \
         patch("backend.tasks.consumer.SpiderResultRepository", return_value=repo), \
         patch("backend.tasks.consumer.SpiderTaskConsumer._engine",
               staticmethod(lambda: object())):
        await consumer._flush_batch([msg], {8: 1})

    session.add_all.assert_not_called()
    consumer._fail_task.assert_awaited()
    assert consumer._fail_task.await_args.args[0] == 8
    assert "入队企业" in consumer._fail_task.await_args.args[1]
    consumer._redis.rpush.assert_awaited()
    dead_key, dead_raw = consumer._redis.rpush.await_args.args
    assert dead_key == DEAD_ITEM_QUEUE
    dead = json.loads(dead_raw)
    assert dead["task_id"] == 8
    assert "入队企业" in dead["_reject_reason"]
    # 计数被扣成 0，不给别的企业加 result_count
    repo.batch_increment_result_counts.assert_awaited()
    assert repo.batch_increment_result_counts.await_args.args[0].get(8, 0) == 0


@pytest.mark.asyncio
async def test_flush_missing_task_not_written():
    """GWT-10.4：任务行不存在 → 不落结果"""
    consumer = SpiderTaskConsumer()
    consumer._redis = AsyncMock()
    consumer._fail_task = AsyncMock()
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.batch_increment_result_counts = AsyncMock()
    session, ctx = _flush_session()
    msg = {"task_id": 9, "spider_name": "s1", "item": {"url": "https://x"}}
    with patch("backend.tasks.consumer.AsyncSession", return_value=ctx), \
         patch("backend.tasks.consumer.SpiderTaskRepository", return_value=repo), \
         patch("backend.tasks.consumer.SpiderResultRepository", return_value=repo), \
         patch("backend.tasks.consumer.SpiderTaskConsumer._engine",
               staticmethod(lambda: object())):
        await consumer._flush_batch([msg], {9: 1})
    session.add_all.assert_not_called()
    consumer._redis.rpush.assert_awaited()


@pytest.mark.asyncio
async def test_ingest_single_orphan_skips_create():
    """单条 _ingest 无入队企业也不写结果"""
    consumer = SpiderTaskConsumer()
    consumer._redis = AsyncMock()
    consumer._fail_task = AsyncMock()
    session = MagicMock()
    session.commit = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    result_repo = MagicMock()
    result_repo.create_for_task = AsyncMock()
    task_repo = MagicMock()
    task_repo.get_by_id = AsyncMock(return_value=MagicMock(params=None, tenant_id=None))
    msg = {"task_id": 4, "spider_name": "example", "item": {"url": "https://a.b"}}
    with (
        patch("backend.tasks.consumer.AsyncSession", return_value=session),
        patch("backend.tasks.consumer.SpiderResultRepository", return_value=result_repo),
        patch("backend.tasks.consumer.SpiderTaskRepository", return_value=task_repo),
        patch("backend.tasks.consumer.SpiderTaskConsumer._engine",
              staticmethod(lambda: object())),
    ):
        await consumer._ingest(msg)
    result_repo.create_for_task.assert_not_awaited()
    consumer._fail_task.assert_awaited()
