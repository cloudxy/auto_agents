"""LLM 直连请求构造 / 响应 content 提取 / 三协议 usage 归一化

拆分自 llm_client.py（规模治理，行为零变化）：重试循环之外、不依赖任何
可 patch 依赖的纯构造/解析步骤。llm_client 原样 re-export 全部名字
（含 _BUSINESS_MAX_TOKENS / _normalize_usage），旧 import 路径不变。

本模块不 import 门面、不 import llm_gateway；settings 经 llm_common.seam() 晚绑定取值。
"""
from dataclasses import dataclass
from typing import Any, Optional

from backend.services.llm_common import LlmRuntimeConfig
from backend.services.llm_common.seam import seam as _seam
from platform_core.exceptions import BusinessException

# B-M3：anthropic/gemini 经适配器构造请求时对话 max_tokens 缺省（openai 兼容路径
# 不注入该字段——保持与历史 payload 字节级一致）
_BUSINESS_MAX_TOKENS = 4096


@dataclass(frozen=True)
class _DirectCall:
    """直连路径一次 llm_chat 的不变量（各次重试共享）"""
    url: str
    headers: dict
    payload: dict
    adapter: Any  # None = openai 兼容历史路径；否则 llm_protocol 适配器
    protocol: str
    model: str
    usage_dim: str
    budget: int
    tenant_id: Optional[int]


def _assert_direct_config(cfg: LlmRuntimeConfig) -> None:
    """直连路径前置校验：base_url / model / api_key 缺失即抛业务异常"""
    if not cfg.base_url or not cfg.model:
        raise BusinessException(
            "LLM 配置不完整：请检查 LLM.BASE_URL / LLM.MODEL（或激活供应商的配置）"
        )
    if not cfg.api_key:
        raise BusinessException(
            "缺少 LLM API Key：请在 .env 配置 LLM_API_KEY（或为激活的供应商配置密钥）"
        )


def _resolve_budget(budget_override: Optional[int]) -> int:
    """token 预算：调用方独立预算优先，否则沿用全局 LLM.MAX_TOKENS_BUDGET"""
    if budget_override is not None:
        return budget_override
    return int(_seam().settings.get("LLM.MAX_TOKENS_BUDGET", 200000))


def _prepare_direct_call(
    messages: list[dict],
    cfg: LlmRuntimeConfig,
    usage_dim: Optional[str],
    budget_override: Optional[int],
    model_override: Optional[str],
) -> _DirectCall:
    """直连请求构造：openai 兼容走历史 payload，其余协议经 llm_protocol 适配器"""
    budget = _resolve_budget(budget_override)
    protocol = getattr(cfg, "protocol", "openai_compatible") or "openai_compatible"
    effective_model = model_override or cfg.model
    if protocol == "openai_compatible":
        # 历史路径原样构造（零回归硬约束：payload 不新增字段）
        payload = {"model": effective_model, "messages": messages, "temperature": cfg.temperature}
        headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
        url = f"{cfg.base_url}/chat/completions"
        adapter = None
    else:
        from backend.services.llm_protocol import get_adapter as _get_adapter

        adapter = _get_adapter(protocol)
        _req = adapter.build_chat(
            cfg.base_url, cfg.api_key, effective_model, messages, max_tokens=_BUSINESS_MAX_TOKENS
        )
        url, headers, payload = _req.url, _req.headers, _req.json_payload
    # token 用量按 provider 维度计数（兜底路径统一记在 "config" 名下）；调用方可覆盖维度
    dim = f"provider:{cfg.provider_id}" if cfg.provider_id is not None else "config"
    from platform_core.tenant_context import current_tenant_id as _cur_tid

    return _DirectCall(
        url=url, headers=headers, payload=payload, adapter=adapter, protocol=protocol,
        model=effective_model, usage_dim=usage_dim or dim, budget=budget, tenant_id=_cur_tid(),
    )


def _openai_content(data: dict):
    """openai 兼容响应取 choices[0].message.content（缺字段得 None）"""
    return ((data.get("choices") or [{}])[0].get("message") or {}).get("content")


def _normalize_usage(protocol: str, data: dict) -> dict[str, int]:
    """三协议 usage 归一化：openai {prompt/completion/total}；anthropic
    {input_tokens/output_tokens}；gemini {usageMetadata{promptTokenCount/
    candidatesTokenCount/totalTokenCount}} → 统一 {prompt, completion, total}"""
    usage = data.get("usage") or {}
    if protocol == "anthropic":
        prompt = int(usage.get("input_tokens") or 0)
        completion = int(usage.get("output_tokens") or 0)
        return {"prompt": prompt, "completion": completion, "total": prompt + completion}
    if protocol == "google_gemini":
        meta = data.get("usageMetadata") or {}
        prompt = int(meta.get("promptTokenCount") or 0)
        completion = int(meta.get("candidatesTokenCount") or meta.get("candidateTokenCount") or 0)
        total = int(meta.get("totalTokenCount") or (prompt + completion))
        return {"prompt": prompt, "completion": completion, "total": total}
    return {
        "prompt": int(usage.get("prompt_tokens") or 0),
        "completion": int(usage.get("completion_tokens") or 0),
        "total": int(usage.get("total_tokens") or 0),
    }
