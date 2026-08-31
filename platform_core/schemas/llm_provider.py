"""LLM 供应商 Schema —— 多供应商管理契约（CRUD / 激活 / 连通性测试）

前端契约（已对齐）：GET /llm/providers 直出数组（无信封无分页），
响应字段为 api_key_masked；PUT 时 api_key 留空表示不修改；
test 端点返回 {ok, latency_ms, model, error}。

安全约定：
- api_key 明文仅出现在 Create/Update 请求体，永不出服务层；
  Response.api_key_masked 一律输出掩码（***<尾4位>，无密钥则空串），不泄露明文
- base_url 校验必须 http/https 且含主机名；恒拒绝云元数据端点
  （link-local 169.254.0.0/16 字面量与 metadata.* 域名，SSRF 高危目标）；
  私网/环回（本地 new-api/ollama 为文档化合法路径）是否禁用由服务层
  LLM.PROVIDER_BLOCK_PRIVATE_URL 开关决定
- is_active 不在 Create/Update 中开放（激活走专用端点 /activate，保证单激活互斥）
"""
import ipaddress
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from platform_core.schemas.base import RequestBody

# 协议白名单（B-M1：经 llm_protocol 适配器支持三协议）
PROVIDER_TYPES = ("openai_compatible", "anthropic", "google_gemini")

# link-local 元数据网段（RFC 3927，云厂商 metadata 服务所在地址段，恒拒绝）
_LINK_LOCAL_NET = ipaddress.ip_network("169.254.0.0/16")
# 本机/内网特殊域名后缀（M6 同款口径：DNS 级校验无法覆盖的静态拒绝项）
_LOCAL_HOST_SUFFIXES = (".localhost", ".local", ".internal")


def mask_api_key(plain: Optional[str]) -> str:
    """API Key 掩码：***<尾4位>；无密钥（None/空串）返回空串"""
    if not plain:
        return ""
    tail = plain[-4:] if len(plain) >= 4 else plain
    return f"***{tail}"


def is_metadata_host(hostname: str) -> bool:
    """host 是否为云元数据端点特征（恒拒绝项，不受 PROVIDER_BLOCK_PRIVATE_URL 影响）

    - link-local 字面量 IP（169.254.0.0/16，含 AWS/GCP metadata 地址）
    - metadata.* 类域名（如 metadata.google.internal）
    """
    host = (hostname or "").lower().rstrip(".")
    if not host:
        return False
    if host.startswith("metadata"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip in _LINK_LOCAL_NET


def is_private_base_url(url: str) -> bool:
    """base_url 是否指向私网/环回/保留地址（M6 式静态判定，供服务层开关校验复用）

    仅判定 host 字面量与特征域名；不做 DNS 解析（域名目标的解析级校验
    由调用方按需在运行时执行）。与 ai_plan 的 M6 校验差异说明：
    LLM base_url 允许任意端口（如本地 new-api localhost:3000），
    故不沿用 Web 抓取的 80/443 端口白名单，抽出独立工具函数避免
    schemas 同层交叉 import（评审 M-1 的 import 方向取舍）。
    """
    host = (urlparse(url or "").hostname or "").lower().rstrip(".")
    if not host:
        return False
    if host == "localhost" or host.endswith(_LOCAL_HOST_SUFFIXES):
        return True
    if host.isdigit():
        # 纯数字 host：glibc 解析语义下命中整数编码 IP（如 2130706433→127.0.0.1）
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # 域名目标：静态判定到此为止
    return not ip.is_global


def _validate_base_url(v: str) -> str:
    """base_url 必须 http/https 且含主机名（去掉首尾空白与末尾斜杠后存储）

    恒拒绝云元数据端点（link-local 字面量与 metadata.* 域名）——SSRF 高危
    目标且无合法业务场景；私网/环回是否放行由服务层
    LLM.PROVIDER_BLOCK_PRIVATE_URL 开关决定（本地 new-api/ollama 属合法路径）。
    """
    v = (v or "").strip().rstrip("/")
    if not v:
        raise ValueError("base_url 不能为空")
    parsed = urlparse(v)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("base_url 必须是 http/https 地址")
    hostname = parsed.hostname or ""
    if not hostname:
        raise ValueError("base_url 缺少主机名")
    if is_metadata_host(hostname):
        raise ValueError("base_url 不允许指向云元数据端点（link-local/metadata 地址）")
    return v


class ProviderModelEntry(RequestBody):
    """供应商模型条目（PUT /providers/{id}/models 全量替换语义的元素）"""

    model_id: str = Field(..., min_length=1, max_length=128)
    alias: str = Field("", max_length=128)
    model_tier: str = Field("basic", pattern=r"^(strong|basic)$")
    priority: int = Field(100, ge=0, le=10000)
    is_default: bool = False
    enabled: bool = True


class ProviderModelsUpdate(RequestBody):
    """全量替换请求体；is_default 至多一行（多行 422 由服务层校验）"""

    models: list[ProviderModelEntry] = Field(..., min_length=0, max_length=200)


class LlmProviderCreate(RequestBody):
    """创建 LLM 供应商请求（api_key 可选；未配置主密钥时带 api_key 会被服务层拒绝）"""

    name: str = Field(..., min_length=1, max_length=100, description="供应商名称（唯一）")
    provider_type: str = Field("openai_compatible", max_length=50,
                               description="协议类型（当前仅 openai_compatible）")
    base_url: str = Field(..., min_length=1, max_length=500, description="API 基地址（http/https）")
    api_key: Optional[str] = Field(None, max_length=500, description="API Key 明文（仅入参，落库为密文）")
    model: str = Field(..., min_length=1, max_length=100, description="默认模型名")
    temperature: float = Field(0.2, ge=0, le=2, description="采样温度（0-2）")
    timeout: int = Field(120, ge=1, le=600, description="单次请求超时（秒）")
    max_retries: int = Field(3, ge=1, le=10, description="指数退避重试次数")
    enabled: bool = Field(True, description="是否启用")
    remark: Optional[str] = Field(None, max_length=255, description="备注")

    @field_validator("base_url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        return _validate_base_url(v)

    @field_validator("provider_type")
    @classmethod
    def _validate_provider_type(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in PROVIDER_TYPES:
            raise ValueError(f"不支持的供应商类型: {v}（仅 {'/'.join(PROVIDER_TYPES)}）")
        return v
    # B-M2 向导流：创建时一并落模型子表（可选；默认模型取 is_default 行）
    models: list[ProviderModelEntry] = Field(default_factory=list)


class LlmProviderUpdate(RequestBody):
    """更新 LLM 供应商请求（PATCH 语义：仅提交的字段生效；api_key 留空不修改）"""

    name: Optional[str] = Field(None, min_length=1, max_length=100, description="供应商名称")
    provider_type: Optional[str] = Field(None, max_length=50, description="协议类型")
    base_url: Optional[str] = Field(None, min_length=1, max_length=500, description="API 基地址")
    api_key: Optional[str] = Field(None, max_length=500,
                                   description="API Key 明文（留空/不传不修改，非空重新加密落库）")
    model: Optional[str] = Field(None, min_length=1, max_length=100, description="默认模型名")
    temperature: Optional[float] = Field(None, ge=0, le=2, description="采样温度")
    timeout: Optional[int] = Field(None, ge=1, le=600, description="单次请求超时（秒）")
    max_retries: Optional[int] = Field(None, ge=1, le=10, description="重试次数")
    enabled: Optional[bool] = Field(None, description="是否启用")
    remark: Optional[str] = Field(None, max_length=255, description="备注")

    @field_validator("base_url")
    @classmethod
    def _validate_url(cls, v: Optional[str]) -> Optional[str]:
        return _validate_base_url(v) if v is not None else v

    @field_validator("provider_type")
    @classmethod
    def _validate_provider_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in PROVIDER_TYPES:
            raise ValueError(f"不支持的供应商类型: {v}（仅 {'/'.join(PROVIDER_TYPES)}）")
        return v


class LlmProviderResponse(BaseModel):
    """LLM 供应商响应快照（api_key_masked 恒为掩码，绝不回传明文）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    provider_type: str
    base_url: str
    api_key_masked: str = Field("", description="API Key 掩码（***<尾4位>，无密钥为空串）")
    model: str
    temperature: float
    timeout: int
    max_retries: int
    is_active: bool = False
    enabled: bool = True
    remark: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class LlmProviderTestResponse(BaseModel):
    """供应商连通性测试结果（不落库）"""

    ok: bool = Field(..., description="连通是否成功")
    latency_ms: int = Field(..., description="耗时（毫秒）")
    model: str = Field(..., description="测试使用的模型名")
    error: Optional[str] = Field(None, description="失败原因（成功为 null）")
