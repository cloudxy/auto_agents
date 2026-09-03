"""LLM 探测引擎（B2，工单 82 拆分自 llm_provider_service.py）

保存前探测（key 仅本次请求使用，不落库不落日志不回显）：
- probe_models：拉取平台模型列表（归一化 + 对话模型计数）
- probe_test：1-token 连通测试（表单当前 平台/地址/Key/模型 真发一次）
入库后测试：
- test_connectivity：向已存供应商 {base_url}/chat/completions 发 1-token 探测
"""
import time

import httpx

from backend.repositories.llm_provider_repository import LlmProviderRepository
from backend.services.llm_protocol import ProtocolError, execute_json, get_adapter
from backend.services.llm_secret_vault import LlmSecretVault
from platform_core.exceptions import NotFoundException
from platform_core.logger import get_logger
from platform_core.schemas.llm_provider import LlmProviderTestResponse

logger = get_logger("service.llm_probe")

_PROBE_TIMEOUT_SECONDS = 10.0
_PROBE_MAX_TOKENS = 16


class LlmProbeEngine:
    """探测引擎（无实例状态；test_connectivity 注入 repo）"""

    @staticmethod
    async def probe_models(provider_type: str, base_url: str, api_key: str) -> dict:
        """拉取平台模型列表（归一化 + 对话模型计数）"""
        logger.info(f"模型列表探测 | type={provider_type} host={LlmSecretVault.host_of(base_url)}")
        validated = LlmSecretVault.validated_probe_base_url(base_url)
        adapter = get_adapter(provider_type)
        models = await adapter.list_models(validated, api_key)
        chat_only = models.chat_only()
        return {
            "models": [{"id": m.id, "owned_by": m.owned_by} for m in models],
            "chat_only_count": len(chat_only),
        }

    @staticmethod
    async def probe_test(provider_type: str, base_url: str, api_key: str, model: str) -> dict:
        """1-token 连通测试（保存前）——用表单当前 平台/地址/Key/模型 真发一次"""
        logger.info(f"连通探测 | type={provider_type} host={LlmSecretVault.host_of(base_url)} model={model}")
        validated = LlmSecretVault.validated_probe_base_url(base_url)
        adapter = get_adapter(provider_type)
        request = adapter.build_chat(
            validated, api_key, model, [{"role": "user", "content": "ping"}], max_tokens=_PROBE_MAX_TOKENS
        )
        started = time.perf_counter()
        try:
            data = await execute_json(None, "POST", request.url, request.headers, request.json_payload)
            content = adapter.parse_chat(data)
            if not content:
                raise ProtocolError("HTTP 200 响应缺少文本内容")
            return {
                "ok": True, "latency_ms": int((time.perf_counter() - started) * 1000),
                "model": model, "error": "",
            }
        except ProtocolError as exc:
            return {
                "ok": False, "latency_ms": int((time.perf_counter() - started) * 1000),
                "model": model, "error": str(exc),
            }

    @staticmethod
    async def test_connectivity(repo: LlmProviderRepository, provider_id: int) -> LlmProviderTestResponse:
        """向 {base_url}/chat/completions 发 1-token 探测请求，返回延迟与错误摘要"""
        logger.info(f"入库连通测试 | provider={provider_id}")
        item = await repo.get_by_id(provider_id)
        if item is None:
            raise NotFoundException("LLM 供应商")
        base_url = str(item.base_url or "").rstrip("/")
        model = str(item.model or "")
        api_key = LlmSecretVault.decrypt_api_key(getattr(item, "api_key_encrypted", None))

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": _PROBE_MAX_TOKENS,
        }

        start = time.perf_counter()
        try:
            # trust_env=False：供应商 base_url 可能指向本机 mock/内网端点，
            # 不读环境变量与 macOS 系统代理（与 notify/newapi 服务的 client 约定一致）
            async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_SECONDS, trust_env=False) as client:
                resp = await client.post(f"{base_url}/chat/completions",
                                         json=payload, headers=headers)
                latency_ms = int((time.perf_counter() - start) * 1000)
                if resp.status_code == 200:
                    logger.info(f"LLM 连通性测试通过: id={provider_id}, latency={latency_ms}ms")
                    return LlmProviderTestResponse(ok=True, latency_ms=latency_ms, model=model)
                # 错误信息脱敏（评审 M-1）：仅回显状态码与标准化原因短语，
                # 不回显响应体（可能含上游密钥/内网信息）
                reason = str(getattr(resp, "reason_phrase", "") or "").strip()
                return LlmProviderTestResponse(
                    ok=False, latency_ms=latency_ms, model=model,
                    error=f"HTTP {resp.status_code} {reason}".strip(),
                )
        except Exception as e:  # noqa: BLE001 网络异常统一转结构化失败结果
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.warning(f"LLM 连通性测试失败: id={provider_id}, error={e}")
            return LlmProviderTestResponse(
                ok=False, latency_ms=latency_ms, model=model, error=str(e)[:500]
            )
