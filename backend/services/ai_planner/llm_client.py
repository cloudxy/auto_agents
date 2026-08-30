"""LLM 客户端层：共享 httpx client 缓存 / 运行时配置解析 / chat completions 调用

拆分自 ai_planner_service.py（期4 结构治理），职责边界：
- 共享 AsyncClient 缓存（provider 路径专用）：get_shared_client / invalidate_client_cache，
  含连接池常量与缓存键
- 运行时配置解析（激活供应商优先 / yml+env 兜底）：_resolve_llm_runtime_config /
  resolve_config_from_settings
- chat completions 调用（超时 / 指数退避重试 / token 预算熔断）：llm_chat
- 进程级 token 用量累计：_TOKEN_USAGE（跨请求熔断）

Patch 兼容约定：存量单测 patch backend.services.ai_planner_service.<name>（门面路径），
本模块对可 patch 的可变依赖（settings / _TOKEN_USAGE / _resolve_llm_runtime_config /
get_shared_client 等）一律经门面模块 _facade 属性查找（文件末行 import，保证
shim ↔ 包双向初始化顺序均安全），使旧 patch 路径在运行时生效；httpx 为全局共享
模块对象（patch httpx.AsyncClient 即全局生效），保留本地引用即可。
"""
import asyncio
import hashlib
import os
from typing import Optional

import httpx

from backend.services.llm_provider_service import LlmProviderService, LlmRuntimeConfig
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger

logger = get_logger("api")

# LLM 重试退避基数（指数：1s/2s/4s...）
_RETRY_BASE_DELAY = 1.0

# 进程级 token 用量累计（跨请求熔断；按 provider 维度计数，兜底路径统一记在
# "config" 名下；单实例假设：多副本部署时预算无法跨进程聚合，需外部聚合方案）
_TOKEN_USAGE: dict[str, int] = {}

# ----------------------------------------------------------------------
# 共享 AsyncClient 缓存（provider 路径专用；兜底路径保持现状的一次性 client）
# ----------------------------------------------------------------------
# key=(base_url, sha256(api_key)[:12])：Authorization 头在创建时固化，密钥轮换
# 自然产生新条目；owner 记录归属供应商，热切换/变更/删除时由 invalidate 定向关闭
_HTTP_CLIENTS: dict[tuple[str, str], httpx.AsyncClient] = {}
_HTTP_CLIENT_OWNER: dict[tuple[str, str], int] = {}
# 连接池与超时拆分：connect 上限 10s，读/写/取池跟随调用方超时
_CLIENT_MAX_CONNECTIONS = 20
_CLIENT_MAX_KEEPALIVE_CONNECTIONS = 10
_CLIENT_KEEPALIVE_EXPIRY = 30.0
_CLIENT_CONNECT_TIMEOUT = 10.0


def _client_cache_key(base_url: str, api_key: str) -> tuple[str, str]:
    """共享 client 缓存键：base_url + 密钥指纹（明文/完整哈希均不落内存键）"""
    return (base_url.rstrip("/"), hashlib.sha256((api_key or "").encode("utf-8")).hexdigest()[:12])


async def get_shared_client(base_url: str, api_key: str, timeout: float, provider_id: Optional[int] = None) -> httpx.AsyncClient:
    logger.debug(f"获取共享 LLM client: provider_id={provider_id}, timeout={timeout}")
    # 取（或建）共享 AsyncClient：连接池复用，Limits + connect/read 超时拆分
    key = _client_cache_key(base_url, api_key)
    client = _HTTP_CLIENTS.get(key)
    if client is not None and not client.is_closed:
        return client
    if client is not None:  # 已被外部关闭的残留条目
        _HTTP_CLIENTS.pop(key, None)
        _HTTP_CLIENT_OWNER.pop(key, None)
    limits = httpx.Limits(
        max_connections=_CLIENT_MAX_CONNECTIONS,
        max_keepalive_connections=_CLIENT_MAX_KEEPALIVE_CONNECTIONS,
        keepalive_expiry=_CLIENT_KEEPALIVE_EXPIRY,
    )
    timeout_cfg = httpx.Timeout(
        timeout,
        connect=min(_CLIENT_CONNECT_TIMEOUT, timeout),
        read=timeout, write=timeout, pool=timeout,
    )
    # trust_env=False：不读环境变量与系统代理（对齐 notify/newapi/llm_provider 约定，
    # 规避本机代理软件如 Clash 劫持 httpx 请求返回 502 的陷阱）
    client = httpx.AsyncClient(
        timeout=timeout_cfg, limits=limits, follow_redirects=False, trust_env=False,
    )
    _HTTP_CLIENTS[key] = client
    if provider_id is not None:
        _HTTP_CLIENT_OWNER[key] = provider_id
    return client


async def invalidate_client_cache(provider_id: Optional[int] = None) -> None:
    logger.debug(f"失效共享 LLM client 缓存: provider_id={provider_id}")
    # 失效共享 client 缓存：provider_id 定向清理该供应商的连接，None 全清。
    # 须在事件循环内 await 调用（供应商变更/热切换/删除后由 Service 层触发）；
    # 飞行中的请求不受影响，下次重试自动建新 client。
    keys = [k for k, owner in _HTTP_CLIENT_OWNER.items()
            if provider_id is None or owner == provider_id]
    for key in keys:
        client = _HTTP_CLIENTS.pop(key, None)
        _HTTP_CLIENT_OWNER.pop(key, None)
        if client is None:
            continue
        try:
            await client.aclose()
        except Exception as e:  # noqa: BLE001 关闭失败仅记日志，不影响主流程
            logger.warning(f"共享 LLM client 关闭失败（忽略）: {e}")


# ----------------------------------------------------------------------
# 运行时配置解析（provider 优先 / yml+env 兜底）
# ----------------------------------------------------------------------
def resolve_config_from_settings() -> LlmRuntimeConfig:
    logger.debug("解析 yml/env 兜底 LLM 配置")
    # yml/env 兜底配置：读取顺序与阶段一 _llm_chat 完全一致（零回归保证）。
    # settings 读取必须经门面命名空间（_facade.settings）：test_ai_planner.py /
    # test_llm_provider.py 对 backend.services.ai_planner_service.settings 的
    # monkeypatch 只对门面命名空间的 settings 绑定生效，兜底路径行为契约
    # 与拆分前完全一致。
    return LlmRuntimeConfig(
        base_url=str(_facade.settings.get("LLM.BASE_URL", "") or "").rstrip("/"),
        api_key=os.environ.get("LLM_API_KEY") or str(_facade.settings.get("LLM.API_KEY", "") or ""),
        model=str(_facade.settings.get("LLM.MODEL", "") or ""),
        temperature=float(_facade.settings.get("LLM.TEMPERATURE", 0.2)),
        timeout=float(_facade.settings.get("LLM.TIMEOUT", 120)),
        max_retries=max(1, int(_facade.settings.get("LLM.MAX_RETRIES", 3))),
        enabled=bool(_facade.settings.get("LLM.ENABLED", False)),
        source="config",
        provider_id=None,
    )


async def _resolve_llm_runtime_config() -> LlmRuntimeConfig:
    """独立短事务 session 解析 LLM 运行时配置（激活供应商优先）

    短事务模式同 _read_task_snapshot（每轮新建、查完即关）；任何异常
    （DB 不可用/表未建/单测无库）都降级为 yml/env 兜底，不阻断 LLM 调用。
    """
    try:
        manager = _facade.get_manager()
        async with _facade.AsyncSession(manager.async_engines["DEFAULT"]) as session:
            return await LlmProviderService(session).resolve_runtime_config()
    except Exception as e:  # noqa: BLE001 无库/异常场景一律回退兜底路径
        logger.warning(f"LLM 供应商配置解析失败，回退 yml/env 兜底: {e}")
        return _facade.resolve_config_from_settings()


async def llm_chat(messages: list[dict]) -> str:
    """chat completions：超时 / 指数退避重试 / token 预算熔断 / 未启用抛业务异常

    原 AiPlannerService._llm_chat 方法体（拆分后委托调用，行为零变化）。
    配置来源：激活且 enabled 的供应商优先（provider 路径，共享 client），
    否则 yml/env 兜底（行为与阶段一完全一致，一次性 client）。
    """
    cfg = await _facade._resolve_llm_runtime_config()
    if not cfg.enabled:
        raise BusinessException(
            "LLM 功能未启用（无激活供应商且 LLM.ENABLED=false）："
            "请在 LLM 供应商管理中配置并激活，或开启 LLM.ENABLED 并配置 LLM_API_KEY"
        )
    if not cfg.base_url or not cfg.model:
        raise BusinessException(
            "LLM 配置不完整：请检查 LLM.BASE_URL / LLM.MODEL（或激活供应商的配置）"
        )
    if not cfg.api_key:
        raise BusinessException(
            "缺少 LLM API Key：请在 .env 配置 LLM_API_KEY（或为激活的供应商配置密钥）"
        )

    # token 预算沿用全局 LLM.MAX_TOKENS_BUDGET（供应商表无独立预算列）
    budget = int(_facade.settings.get("LLM.MAX_TOKENS_BUDGET", 200000))
    payload = {"model": cfg.model, "messages": messages, "temperature": cfg.temperature}
    headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
    url = f"{cfg.base_url}/chat/completions"
    # token 用量按 provider 维度计数（兜底路径统一记在 "config" 名下）
    usage_dim = f"provider:{cfg.provider_id}" if cfg.provider_id is not None else "config"
    last_error: Exception | None = None

    for attempt in range(cfg.max_retries):
        used_total = _facade._TOKEN_USAGE.get(usage_dim, 0)
        if used_total >= budget:
            raise BusinessException(
                f"LLM token 预算已耗尽（{usage_dim} 累计 {used_total} >= {budget}），已熔断"
            )
        try:
            if cfg.provider_id is not None:
                # provider 路径：模块级共享 client（连接池复用，变更时 invalidate 失效）
                client = await _facade.get_shared_client(
                    cfg.base_url, cfg.api_key, cfg.timeout, cfg.provider_id
                )
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
            else:
                # 兜底路径：与现状完全一致（每调用一次性 client，yml/env 配置）；
                # trust_env=False 不走系统代理（本机代理劫持陷阱，同 provider 路径约定）
                async with httpx.AsyncClient(timeout=cfg.timeout, trust_env=False) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
            data = resp.json()
            content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
            if not content:
                raise ValueError("LLM 响应缺少 content")
            used = int((data.get("usage") or {}).get("total_tokens") or 0)
            if used:
                _facade._TOKEN_USAGE[usage_dim] = _facade._TOKEN_USAGE.get(usage_dim, 0) + used
                logger.info(
                    f"LLM token 用量: +{used}（{usage_dim} 累计 "
                    f"{_facade._TOKEN_USAGE[usage_dim]}/{budget}）"
                )
            return content
        except BusinessException:
            raise
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if 400 <= status < 500 and status != 429:
                raise BusinessException(f"LLM 请求被拒绝（HTTP {status}），不重试: {e}")
            last_error = e
        except Exception as e:  # noqa: BLE001 超时/网络/解析失败均进入重试
            last_error = e
        delay = _RETRY_BASE_DELAY * (2 ** attempt)
        logger.warning(
            f"LLM 调用失败（第 {attempt + 1}/{cfg.max_retries} 次），"
            f"{delay:.1f}s 后重试: {last_error}"
        )
        await asyncio.sleep(delay)

    raise BusinessException(f"LLM 调用失败（已重试 {cfg.max_retries} 次）: {last_error}")


# ----------------------------------------------------------------------
# 门面引用（循环导入兼容，必须置于文件末尾）
# ----------------------------------------------------------------------
# 薄 shim backend.services.ai_planner_service re-export 本包符号；本模块对可
# patch 的可变依赖经 _facade 属性查找，使旧 patch 路径继续生效。import 置于
# 末尾保证「先 shim 后包」与「先包后 shim」两个初始化入口均安全（部分初始化
# 的门面模块经 sys.modules 绑定，Python 3.7+ 语义）。
import backend.services.ai_planner_service as _facade  # noqa: E402
