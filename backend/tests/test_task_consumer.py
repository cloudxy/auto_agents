"""任务消费者纯函数单测 - params 中 start URL 的提取约定 + M4 flow 渲染参数透传契约

不连真实 Redis/MySQL：只测纯函数解析分支。
M4 跨层契约：flow 任务 params 含 render_js/wait_for/wait_timeout 时，
start_urls 载荷必须携带 params（flow_generic 从 extra["params"] 读取）；
非 flow 任务载荷结构零变化。
"""
import json
import sys
from pathlib import Path

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
