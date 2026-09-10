"""Prompt 构造与 LLM 响应解析（纯函数层）

拆分自 ai_planner_service.py（期4 结构治理），职责边界：
- LLM 响应解析：_parse_llm_json（剥 markdown 围栏 / 提取首尾大括号，严格 JSON dict）
- Prompt 构造：_build_plan_messages（规划）/ _build_repair_messages（自动修复）
- FlowConfig → 任务参数：_build_generated_params（顶层键与 flow_generic 消费者契约一致）
- 注册命名推导：_domain_of / _derive_spider_name

本模块为无副作用纯函数，无外部可变依赖，直接被 orchestrator 经门面调用
（门面 re-export 保证旧 patch/import 路径兼容）。
"""
import json
import re
from urllib.parse import urlparse

from platform_core.schemas.ai_plan import FlowConfig

# LLM 响应中 markdown 代码围栏提取
_MD_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

# ----------------------------------------------------------------------
# Prompt 构造
# ----------------------------------------------------------------------
_PLAN_SYSTEM_PROMPT = (
    "你是网页采集规则生成专家。根据给定的 HTML 片段为流程化爬虫生成采集规则。"
    "只输出一个 JSON 对象，不要任何解释、注释或 markdown 代码块围栏。"
)

_SCHEMA_HINT = (
    '{"selectors": [{"name": "field_name", "type": "xpath|css|regex", "expr": "..."}],'
    ' "pagination": {"selector": "next-page css/xpath selector", "type": "css|xpath",'
    ' "max_pages": 2} | null,'
    ' "detail": {"list_selector": "list-item css", "url_selector": "link xpath (e.g. ./@href)",'
    ' "selectors": [{"name": "...", "type": "...", "expr": "..."}]} | null,'
    ' "filters": [{"field": "field_name", "op": "contains|equals|regex", "value": "..."}]}'
)

_CONSTRAINTS = (
    "约束：selectors 必填且至少 1 条；pagination.selector 与 detail.list_selector 用 css；"
    "detail.url_selector 必须是 xpath；max_pages 固定为 2；只提取页面上真实存在的结构。"
)


def _parse_llm_json(raw: str) -> dict:
    """解析 LLM 响应为严格 JSON dict（剥 markdown 围栏 / 提取首尾大括号）"""
    text = (raw or "").strip()
    match = _MD_FENCE.search(text)
    if match:
        text = match.group(1).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("LLM 响应中未找到 JSON 对象")
        text = text[start:end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM 响应不是合法 JSON: {e}")
    if not isinstance(data, dict):
        raise ValueError("LLM 响应 JSON 顶层必须是对象")
    return data


def _build_plan_messages(target_url: str, html: str) -> list[dict]:
    """规划 prompt：目标 URL + 清洗后 HTML → 采集规则 JSON"""
    user = (
        f"目标页面: {target_url}\n"
        f"HTML 片段（已清洗截断）:\n{html}\n\n"
        f"请输出符合以下结构的 JSON：\n{_SCHEMA_HINT}\n\n{_CONSTRAINTS}"
    )
    return [
        {"role": "system", "content": _PLAN_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _build_repair_messages(target_url: str, flow_dict: dict, reason: str, html: str) -> list[dict]:
    """自动修复 prompt：失败原因 + 原规则 + 样本 HTML → 修正后的完整 JSON"""
    user = (
        f"目标页面: {target_url}\n"
        f"上一次生成的采集规则（试采失败）:\n{json.dumps(flow_dict, ensure_ascii=False)}\n"
        f"试采失败原因: {reason}\n"
        f"HTML 片段（已清洗截断）:\n{html}\n\n"
        f"请根据失败原因修正采集规则，输出完整 JSON（不是差异补丁）：\n{_SCHEMA_HINT}\n\n{_CONSTRAINTS}"
    )
    return [
        {"role": "system", "content": _PLAN_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _build_generated_params(target_url: str, flow: FlowConfig) -> dict:
    """FlowConfig → flow_generic 任务参数（顶层键与消费者 extract_flow 契约一致）"""
    params: dict = {"urls": [target_url]}
    params["selectors"] = [s.model_dump() for s in flow.selectors]
    if flow.pagination is not None:
        params["pagination"] = flow.pagination.model_dump()
    if flow.detail is not None:
        params["detail"] = flow.detail.model_dump()
    if flow.filters:
        params["filters"] = [f.model_dump() for f in flow.filters]
    if flow.render_js:
        params["render_js"] = True
    if flow.wait_for:
        params["wait_for"] = flow.wait_for
    if flow.wait_timeout:
        params["wait_timeout"] = flow.wait_timeout
    return params


def _domain_of(url: str) -> str:
    """提取 URL 域名（注册表命名用）"""
    host = (urlparse(url).netloc or url).split("@")[-1]
    return host or url


def _derive_spider_name(url: str, plan_id: int) -> str:
    """从目标域名推导注册爬虫名（ai_ 前缀 + plan id 保证唯一，总长 ≤50）"""
    slug = re.sub(r"[^a-z0-9]+", "_", _domain_of(url).lower()).strip("_") or "site"
    # i4：name 列上限 50，slug 截断长度按 plan_id 位数动态计算（固定 40 位在 6 位以上 id 时溢出）
    plan_digits = max(1, len(str(plan_id)))
    slug_cap = 50 - len("ai_") - plan_digits - 1
    return f"ai_{slug[:slug_cap]}_{plan_id}"
