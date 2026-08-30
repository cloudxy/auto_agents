"""流程化采集通用爬虫（阶段 5.1，借鉴 EasySpider 流程理念，自研实现）

任务条目经独立队列 `flow_generic:start_urls` 以 JSON 投递（消费者识别流程参数后包装）：
    {"url": "https://...", "task_id": 123,
     "flow": {"selectors": [...],
              "pagination": {"selector", "type": "css|xpath", "max_pages": 10},
              "detail": {"list_selector", "url_selector", "selectors": [...]},
              "filters": [{"field", "op": "contains|equals|regex", "value"}]}}

parse 状态机（stage 走请求 meta）：
- stage=list（默认）：按 selectors 提取字段 → filters 过滤 →
  有 detail 配置：按 list_selector 逐项取 url_selector 链接，发 stage=detail 请求；
  有 pagination 配置且未达 max_pages：提取下一页链接发请求（dont_filter）。
- stage=detail：按详情页 selectors 提取字段产出 Item。
列表页与详情页均产出 BaseItem（content=字段 JSON，source="flow"）。

红线：翻页请求数受 max_pages 约束；反爬配置（下载延时等）走 scrapy settings，
任务参数不允许覆盖。
"""
import re

from scrapy import Request
from scrapy.exceptions import DropItem
from scrapy_redis.spiders import RedisSpider

from platform_core.logger import get_logger
from spiders.base import parse_queue_entry
from utils.selector_engine import build_item, extract_fields

logger = get_logger("spider")

_FILTER_OPS = ("contains", "equals", "regex")
_LINK_SELECTOR_TYPES = ("css", "xpath")

# 单任务翻页上限兜底：防止参数漏配时无限翻页（默认值见 max_pages 归一化）
_DEFAULT_MAX_PAGES = 10
_MAX_PAGES_CAP = 100


def _apply_filters(fields: dict, filters: list) -> dict:
    """条件过滤：按字段值逐条过滤（未知字段/非法操作符跳过）"""
    for rule in filters:
        field = rule.get("field")
        op = rule.get("op")
        value = rule.get("value")
        if not field or op not in _FILTER_OPS or field not in fields:
            logger.warning(f"非法过滤规则已跳过: {rule!r}")
            continue
        values = fields[field]
        if op == "contains":
            values = [v for v in values if str(value) in v]
        elif op == "equals":
            values = [v for v in values if v == str(value)]
        else:  # regex
            try:
                pattern = re.compile(str(value))
            except re.error as e:
                logger.warning(f"过滤正则非法已跳过: value={value!r}, error={e}")
                continue
            values = [v for v in values if pattern.search(v)]
        fields[field] = values
    return fields


def _normalize_max_pages(pagination: dict) -> int:
    """max_pages 归一化：缺失/非法回退默认值，上限封顶（防无限翻页）"""
    try:
        pages = int(pagination.get("max_pages", _DEFAULT_MAX_PAGES))
    except (TypeError, ValueError):
        pages = _DEFAULT_MAX_PAGES
    return max(1, min(pages, _MAX_PAGES_CAP))


class FlowGenericSpider(RedisSpider):
    """流程化采集爬虫：分页 / 详情页 / 条件过滤状态机"""

    name = "flow_generic"
    redis_key = "flow_generic:start_urls"
    # 采集目标由任务参数指定，不做域名白名单限制（风控由站点侧反爬配置兜底）

    def make_request_from_data(self, data):
        """start_urls 队列条目 → 请求（JSON 携带完整流程定义 + task_id）"""
        url, task_id, extra = parse_queue_entry(data)
        # 非 http(s) 条目（如缺 url 的流程 JSON）直接丢弃，避免把载荷误当 URL 请求
        if not url or not str(url).startswith(("http://", "https://")):
            logger.warning(f"流程爬虫收到非法 URL 条目，丢弃: {data!r}")
            return None
        flow = extra.get("flow") or {}
        if not flow and isinstance(extra.get("selectors"), list) and extra["selectors"]:
            # 兼容：任务已被指派到本爬虫但载荷仅携带顶层 selectors（未经 flow 包装投递），
            # 此时 response.meta.flow 为空会导致选择器为空 → 0 item → 任务永不终态
            flow = {"selectors": extra["selectors"]}
        meta = {"stage": "list", "page": 1, "flow": flow}
        if task_id is not None:
            meta["task_id"] = int(task_id)
        # Playwright 动态渲染支持：任务参数 render_js=true 时启用 JS 渲染
        params = extra.get("params") or {}
        if isinstance(params, dict) and params.get("render_js"):
            meta["render_js"] = True
            if params.get("wait_for"):
                meta["wait_for"] = params["wait_for"]
            if params.get("wait_timeout"):
                meta["wait_timeout"] = int(params["wait_timeout"])
        return Request(url, meta=meta, dont_filter=True)

    def parse(self, response):
        """状态机入口：按 meta.stage 分发列表页 / 详情页解析"""
        stage = response.meta.get("stage", "list")
        if stage == "detail":
            yield from self._parse_detail(response)
        else:
            yield from self._parse_list(response)

    @staticmethod
    def _render_meta(response) -> dict:
        """从当前响应提取 Playwright 渲染相关 meta，透传到后续请求"""
        keys = ("render_js", "wait_for", "wait_timeout")
        return {k: response.meta[k] for k in keys if k in response.meta}

    # ------------------------------------------------------------------
    # stage=list：字段提取 + 过滤 → 详情链接 / 下一页
    # ------------------------------------------------------------------
    def _parse_list(self, response):
        flow = response.meta.get("flow") or {}
        task_id = response.meta.get("task_id")
        page = int(response.meta.get("page", 1))
        logger.info(f"流程采集列表页: {response.url} | page={page}")

        fields = extract_fields(response, flow.get("selectors") or [])
        fields = _apply_filters(fields, flow.get("filters") or [])
        if fields and any(fields.values()):
            yield build_item(response, fields, source="flow")

        # 详情页分支：列表项内取链接发 stage=detail 请求（相对路径用 urljoin 归一）
        detail = flow.get("detail")
        if isinstance(detail, dict) and detail.get("list_selector") and detail.get("url_selector"):
            url_selector = detail["url_selector"]
            try:
                for entry in response.css(detail["list_selector"]):
                    href = entry.xpath(url_selector).get()
                    if href:
                        meta = {
                            "stage": "detail",
                            "flow": flow,
                            **({"task_id": task_id} if task_id is not None else {}),
                            **self._render_meta(response),
                        }
                        yield Request(response.urljoin(href.strip()), meta=meta, dont_filter=True)
            except Exception as e:  # noqa: BLE001 选择器非法不中断整页
                logger.warning(f"详情页链接提取失败: {detail!r}, error={e}")

        # 翻页分支：未达 max_pages 时提取下一页链接继续（dont_filter 防重）
        pagination = flow.get("pagination")
        if isinstance(pagination, dict) and pagination.get("selector"):
            max_pages = _normalize_max_pages(pagination)
            if page >= max_pages:
                logger.info(f"已达最大翻页数，停止翻页: page={page}, max_pages={max_pages}")
            else:
                ptype = pagination.get("type", "css")
                try:
                    if ptype == "xpath":
                        href = response.xpath(pagination["selector"]).get()
                    else:
                        href = response.css(pagination["selector"]).get()
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"下一页选择器执行失败: {pagination!r}, error={e}")
                    href = None
                if href:
                    meta = {
                        "stage": "list",
                        "page": page + 1,
                        "flow": flow,
                        **({"task_id": task_id} if task_id is not None else {}),
                        **self._render_meta(response),
                    }
                    yield Request(response.urljoin(str(href).strip()), meta=meta, dont_filter=True)
                else:
                    logger.info(f"未找到下一页链接，结束翻页: page={page}")

    # ------------------------------------------------------------------
    # stage=detail：按详情页选择器提取字段产出 Item
    # ------------------------------------------------------------------
    def _parse_detail(self, response):
        flow = response.meta.get("flow") or {}
        detail = flow.get("detail") or {}
        logger.info(f"流程采集详情页: {response.url}")

        fields = extract_fields(response, detail.get("selectors") or [])
        fields = _apply_filters(fields, flow.get("filters") or [])
        if not fields or not any(fields.values()):
            raise DropItem(f"详情页未提取到任何字段: {response.url}")
        yield build_item(response, fields, source="flow")
