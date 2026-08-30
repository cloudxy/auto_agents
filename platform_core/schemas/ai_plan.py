"""AI 采集计划 Schema —— LLM 规划契约 + FlowConfig 流程定义校验

FlowConfig 与 scrapy/spiders/flow_generic.py 的 flow JSON 契约严格对齐
（仅复用 JSON 结构，不 import 爬虫代码，B2 边界）：
- selectors：[{name, type: xpath|css|regex, expr}]（selector_engine._SELECTOR_TYPES）
- pagination：{selector, type: css|xpath（翻页链接仅支持这两种）, max_pages: 1-100}
- detail：{list_selector（css）, url_selector（xpath，如 @href）, selectors}
- filters：[{field, op: contains|equals|regex, value}]（flow_generic._FILTER_OPS）
- render_js / wait_for / wait_timeout：任务参数层（消费者透传 Playwright meta）

validators 拒绝非法表达式：regex 必须可编译；xpath/css 走白名单字符校验，
拒绝 javascript:/script 注入片段；wait_for 复用 css 白名单（i2）。
target_url 静态 SSRF 校验（M6）：仅 80/443、拒绝 localhost/字面量私网 IP
（含十进制整数编码），域名目标的 DNS 级校验由服务层在线抓取时执行。
"""
import ipaddress
import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from platform_core.schemas.base import RequestBody

# 与 scrapy/utils/selector_engine.py 的 _SELECTOR_TYPES 一致
SELECTOR_EXPR_TYPES = ("xpath", "css", "regex")
# 与 scrapy/spiders/flow_generic.py 的 _FILTER_OPS 一致
FILTER_OPS = ("contains", "equals", "regex")

# 翻页/详情链接提取仅支持 css|xpath（flow_generic 的 _LINK_SELECTOR_TYPES）
LINK_SELECTOR_TYPES = ("css", "xpath")

_XSS_PATTERNS = ("javascript:", "<script", "onerror=", "onload=")
_XPATH_ALLOWED_START = re.compile(r"^(?:/|//|\.|@|\(|[A-Za-z\*])")

# M6：单页抓取目标仅允许标准 Web 端口（与服务层 SSRF 校验一致）
ALLOWED_TARGET_PORTS = (80, 443)
# M6：本机/内网特殊域名后缀（DNS 级校验无法覆盖的静态拒绝项）
_LOCAL_HOST_SUFFIXES = (".localhost", ".local", ".internal")


def validate_selector_expr(expr: str, expr_type: str) -> str:
    """选择器表达式白名单校验（type 与 expr 组合合法性，非法抛 ValueError）"""
    lowered = expr.lower()
    for pattern in _XSS_PATTERNS:
        if pattern in lowered:
            raise ValueError(f"表达式包含禁止片段 '{pattern}'")
    if expr_type == "regex":
        try:
            re.compile(expr)
        except re.error as e:
            raise ValueError(f"非法正则表达式: {e}")
    elif expr_type == "xpath":
        if not _XPATH_ALLOWED_START.match(expr):
            raise ValueError("xpath 表达式须以 / . // @ 轴或节点名开头")
        if ";" in expr:
            raise ValueError("xpath 表达式不允许包含分号")
    elif expr_type == "css":
        if not re.match(r"^[a-zA-Z0-9\.\#\*\[\]\"'():\s_\-|>,~^$=,@]+$", expr):
            raise ValueError("css 表达式含未允许字符")
    else:
        raise ValueError(f"不支持的表达式类型: {expr_type}（仅 {'/'.join(SELECTOR_EXPR_TYPES)}）")
    return expr


class SelectorRule(BaseModel):
    """字段提取规则（selector_engine.extract_fields 消费格式）"""

    name: str = Field(..., min_length=1, max_length=50, description="字段名")
    type: str = Field(..., pattern="^(xpath|css|regex)$", description="表达式类型")
    expr: str = Field(..., min_length=1, max_length=500, description="选择器表达式")

    @model_validator(mode="after")
    def _validate_expr(self) -> "SelectorRule":
        validate_selector_expr(self.expr, self.type)
        return self


class PaginationConfig(BaseModel):
    """翻页配置（flow_generic._parse_list 翻页分支）"""

    selector: str = Field(..., min_length=1, max_length=500, description="下一页链接选择器")
    type: str = Field("css", pattern="^(css|xpath)$", description="选择器类型（仅 css/xpath）")
    max_pages: int = Field(2, ge=1, le=100, description="最大翻页数（flow_generic 上限封顶 100）")

    @model_validator(mode="after")
    def _validate_selector(self) -> "PaginationConfig":
        validate_selector_expr(self.selector, self.type)
        return self


class DetailConfig(BaseModel):
    """详情页二次采集配置（list_selector 走 css，url_selector 必须是 xpath）"""

    list_selector: str = Field(..., min_length=1, max_length=500, description="列表项 css 选择器")
    url_selector: str = Field(..., min_length=1, max_length=500,
                              description="链接 xpath 表达式（如 ./@href 或 @href）")
    selectors: List[SelectorRule] = Field(default=[], description="详情页字段提取规则")

    @model_validator(mode="after")
    def _validate_selectors(self) -> "DetailConfig":
        validate_selector_expr(self.list_selector, "css")
        validate_selector_expr(self.url_selector, "xpath")
        return self


class FilterRule(BaseModel):
    """条件过滤规则（flow_generic._apply_filters 消费格式）"""

    field: str = Field(..., min_length=1, max_length=50, description="过滤字段名")
    op: str = Field(..., pattern="^(contains|equals|regex)$", description="操作符")
    value: str = Field(..., min_length=1, max_length=500, description="比较值")

    @model_validator(mode="after")
    def _validate_regex_value(self) -> "FilterRule":
        if self.op == "regex":
            try:
                re.compile(self.value)
            except re.error as e:
                raise ValueError(f"过滤正则非法: {e}")
        return self


class FlowConfig(BaseModel):
    """flow_generic 流程定义契约（LLM 规划产出，试采/注册共用）"""

    selectors: List[SelectorRule] = Field(..., min_length=1, description="列表页字段提取规则（至少 1 条）")
    pagination: Optional[PaginationConfig] = Field(None, description="翻页配置（可选）")
    detail: Optional[DetailConfig] = Field(None, description="详情页配置（可选）")
    filters: List[FilterRule] = Field(default=[], description="条件过滤规则（可选）")
    render_js: bool = Field(False, description="是否启用 Playwright JS 渲染")
    wait_for: Optional[str] = Field(None, max_length=200, description="渲染等待的 css 选择器")
    wait_timeout: Optional[int] = Field(None, ge=1, le=120, description="渲染等待超时秒数")

    @field_validator("wait_for")
    @classmethod
    def _validate_wait_for_css(cls, v: Optional[str]) -> Optional[str]:
        """i2：wait_for 是 Playwright 等待的 css 选择器，复用 css 白名单校验"""
        if v:
            validate_selector_expr(v, "css")
        return v


class AiPlanCreate(RequestBody):
    """创建 AI 采集计划请求（html_snippet 可选，预置后跳过在线抓取）"""

    target_url: str = Field(..., min_length=1, max_length=500, description="目标页面 URL")
    html_snippet: Optional[str] = Field(None, max_length=200000,
                                        description="预置页面 HTML（可选，降级为离线规划）")

    @field_validator("target_url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        """M6：创建入口静态 SSRF 校验（不做 DNS；域名目标由服务层抓取时逐跳校验）"""
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("target_url 必须是 http(s) 地址")
        parsed = urlparse(v)
        host = parsed.hostname or ""
        if not host:
            raise ValueError("target_url 缺少主机名")
        if parsed.port is not None and parsed.port not in ALLOWED_TARGET_PORTS:
            raise ValueError("target_url 仅允许 80/443 端口")
        lowered = host.lower().rstrip(".")
        if lowered == "localhost" or lowered.endswith(_LOCAL_HOST_SUFFIXES):
            raise ValueError("target_url 不允许指向本机/内网域名")
        if lowered.isdigit():
            # 纯数字 host：glibc 解析语义下命中整数编码 IP（如 2130706433→127.0.0.1）
            raise ValueError("target_url 不允许纯数字主机（整数编码 IP 绕过）")
        try:
            ip = ipaddress.ip_address(lowered)  # 字面量 IPv4/IPv6（Python 3.9.5+ 不再解析整数形式）
        except ValueError:
            return v  # 域名目标：在线抓取时由服务层做 DNS 级私网校验
        if not ip.is_global:
            raise ValueError("target_url 不允许指向私网/环回/保留地址")
        return v


class AiPlanResponse(BaseModel):
    """AI 采集计划响应快照"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    target_url: str
    status: str
    plan_json: Optional[dict] = None
    generated_params: Optional[dict] = None
    test_task_id: Optional[int] = None
    iteration_count: int = 0
    error_message: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AiPlanListResponse(BaseModel):
    """AI 采集计划分页列表响应"""

    total: int
    items: List[AiPlanResponse]
