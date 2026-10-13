"""LLM 客户端层：共享 httpx client 缓存 / 运行时配置解析入口 / chat completions 调用

拆分自 ai_planner_service.py（期4 结构治理），职责边界：
- 共享 AsyncClient 缓存（provider 路径专用）：get_shared_client / invalidate_client_cache，
  含连接池常量与缓存键（规模治理：实现位于叶子 llm_client_pool，本模块原样 re-export）
- 运行时配置解析入口（激活供应商优先 / yml+env 兜底）：_resolve_llm_runtime_config
  （实现下沉 backend.services.llm_common——T6 解环：本模块不再依赖
  llm_provider_service，配置形状与两段解析均取自公共叶子层）
- chat completions 调用（超时 / 指数退避重试 / token 预算熔断）：llm_chat
  （规模治理拆出的叶子，本模块原样 re-export：直连请求构造与 usage 归一化
  → llm_client_request；套餐闸与用户可见失败文案 → llm_client_quota；
  候选链查询与降质告警 → llm_client_failover。编排 _failover 留在本模块）
- 进程级 token 用量累计：_TOKEN_USAGE（跨请求熔断）

Patch 兼容约定：存量单测 patch backend.services.ai_planner_service.<name>（门面路径），
本模块对可 patch 的可变依赖（settings / _TOKEN_USAGE / _resolve_llm_runtime_config /
get_shared_client 等）一律经 llm_common.seam() 命名空间调用期取值（门面初始化完成
后注入 seam；无文件末尾反向 import，import 图无环），使旧 patch 路径在运行时生效；
httpx 为全局共享模块对象（patch httpx.AsyncClient 即全局生效），保留本地引用即可。
patch 本模块路径的名字（get_month_used / record_usage / chat_completions /
_candidate_chain / _RETRY_BASE_DELAY 等）均在本模块内经模块全局名调用。
"""
import asyncio
from typing import Optional

import httpx

from backend.config_consts import LLM_DATA_PLANE
from backend.services.ai_planner.llm_client_failover import (  # noqa: F401 — 拆出名兼容 re-export
    _candidate_chain,
    _notify_degrade,
    _query_chain,
)
from backend.services.ai_planner.llm_client_pool import (  # noqa: F401 — 拆出名兼容 re-export
    _CLIENT_CONNECT_TIMEOUT,
    _CLIENT_KEEPALIVE_EXPIRY,
    _CLIENT_MAX_CONNECTIONS,
    _CLIENT_MAX_KEEPALIVE_CONNECTIONS,
    _HTTP_CLIENT_OWNER,
    _HTTP_CLIENTS,
    _client_cache_key,
    get_shared_client,
    invalidate_client_cache,
)
from backend.services.ai_planner.llm_client_quota import (  # noqa: F401 — 拆出名兼容 re-export
    _check_llm_tokens,
    _enforce_tenant_token_quota,
    _gateway_unreachable,
    _no_platform_model,
    _provider_error,
)
from backend.services.ai_planner.llm_client_request import (  # noqa: F401 — 拆出名兼容 re-export
    _BUSINESS_MAX_TOKENS,
    _DirectCall,
    _assert_direct_config,
    _normalize_usage,
    _openai_content,
    _prepare_direct_call,
    _resolve_budget,
)
from backend.services.llm_common import (
    LlmRuntimeConfig,
    resolve_config_from_settings,
    resolve_own_tenant_config,
    resolve_runtime_config,
)
from backend.services.llm_gateway.chat import chat_completions, list_v1_models
from backend.services.llm_common.seam import seam as _seam
from backend.services.llm_usage_service import get_month_used, get_platform_day_used, record_usage
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger

logger = get_logger("api")

PLANNING_DISABLED_COPY = "智能规划未开放"
PLANNING_DISABLED_CODE = "PLANNING_DISABLED"
PLANNING_READONLY_COPY = "当前账号不能开始规划"

# LLM 重试退避基数（指数：1s/2s/4s...）
_RETRY_BASE_DELAY = 1.0

# 进程级 token 用量累计（跨请求熔断；按 provider 维度计数，兜底路径统一记在
# "config" 名下；单实例假设：多副本部署时预算无法跨进程聚合，需外部聚合方案）
_TOKEN_USAGE: dict[str, int] = {}


# ----------------------------------------------------------------------
# 运行时配置解析（provider 优先 / yml+env 兜底；实现下沉 llm_common，T6）
# ----------------------------------------------------------------------
def _is_litellm_plane() -> bool:
    plane = str(_seam().settings.get("LLM.DATA_PLANE", LLM_DATA_PLANE) or LLM_DATA_PLANE)
    return plane == "litellm"


def _gateway_runtime_config() -> LlmRuntimeConfig:
    from backend.services.llm_gateway._settings import _base_url, _timeout_sec, _virtual_key

    logger.debug("组装平台网关运行时配置")
    return LlmRuntimeConfig(
        base_url=_base_url(),
        api_key=_virtual_key(),
        model="",
        temperature=float(_seam().settings.get("LLM.TEMPERATURE", 0.2)),
        timeout=_timeout_sec(),
        max_retries=max(1, int(_seam().settings.get("LLM.MAX_RETRIES", 3))),
        enabled=True,
        source="gateway",
        provider_id=None,
        protocol="openai_compatible",
    )


async def _resolve_litellm_runtime_config() -> LlmRuntimeConfig:
    """本企业激活行直连；否则只网关。except 禁止 resolve_config_from_settings。"""
    logger.debug("DATA_PLANE=litellm 解析运行时配置")
    try:
        manager = _seam().get_manager()
        async with _seam().AsyncSession(manager.async_engines["DEFAULT"]) as session:
            own = await resolve_own_tenant_config(session)
        if own is not None:
            return own
    except Exception as e:  # noqa: BLE001 SH-16：禁止落到 yml/env
        logger.warning(f"本企业供应商解析失败，改走平台网关: {e}")
    return _gateway_runtime_config()


async def _resolve_llm_runtime_config() -> LlmRuntimeConfig:
    """独立短事务 session 解析 LLM 运行时配置。

    DATA_PLANE=litellm：本企业激活行，否则只网关（except 禁止 yml/env）。
    DATA_PLANE=providers：激活供应商优先，异常回退 yml/env（expand 回滚窗）。
    """
    if _is_litellm_plane():
        return await _resolve_litellm_runtime_config()
    try:
        manager = _seam().get_manager()
        async with _seam().AsyncSession(manager.async_engines["DEFAULT"]) as session:
            return await resolve_runtime_config(session)
    except Exception as e:  # noqa: BLE001 无库/异常场景一律回退兜底路径
        logger.warning(f"LLM 供应商配置解析失败，回退 yml/env 兜底: {e}")
        return resolve_config_from_settings()


async def _probe_gateway_models(timeout: float) -> list[str]:
    logger.info("探测平台网关模型列表")
    try:
        models = await list_v1_models(timeout=timeout)
    except Exception as exc:  # noqa: BLE001 预检失败 = 网关不可达，禁止 chat outbound
        raise _gateway_unreachable(exc) from exc
    if not models:
        raise _no_platform_model()
    return models


# ----------------------------------------------------------------------
# 预算闸 / 用量记账 / 重试公共步骤（网关路径与直连路径共用）
# ----------------------------------------------------------------------
async def _budget_guard(usage_dim: str, budget: int, tenant_id) -> int:
    """平台 token 预算闸（审计 R2-8 / R2-10 / P0-10：网关路径与供应商路径共用）

    读数优先月度 Redis 聚合（跨重启/多副本有效）；读数不可用时：
    - LLM.BUDGET_FAIL_CLOSED=true（prod）：拒绝调用——预算失去数据支撑宁可拒绝不可放行；
    - false（默认，测试/CI 无 Redis）：回退进程内存计数。
    累计 >= budget 抛 LLM_COST_FUSE；再过平台全局日上限闸。返回当前累计值（日志用）。
    """
    month_used = await get_month_used(usage_dim, tenant_id=tenant_id)
    if month_used is None:
        if bool(_seam().settings.get("LLM.BUDGET_FAIL_CLOSED", False)):
            logger.error(f"LLM 预算读数不可用，fail-closed 拒绝 | dim={usage_dim} tenant={tenant_id}")
            raise BusinessException(
                f"LLM token 预算读数不可用（Redis），fail-closed 拒绝调用: {usage_dim}",
                code="LLM_BUDGET_UNAVAILABLE",
                status_code=503,
            )
        month_used = _seam()._TOKEN_USAGE.get(usage_dim, 0)
    if month_used >= budget:
        raise BusinessException(
            f"平台 LLM 成本熔断：token 预算已耗尽（{usage_dim} 本月累计 {month_used} >= {budget}）",
            code="LLM_COST_FUSE",
        )
    await _platform_day_cap_guard()
    return int(month_used)


async def _platform_day_cap_guard() -> None:
    """决策 D21：免费档也能用平台 LLM → 平台全局日预算上限（0 = 不设上限）

    读数不可用时同样服从 LLM.BUDGET_FAIL_CLOSED；当日累计 >= 上限抛 LLM_PLATFORM_DAILY_CAP。
    """
    day_cap = int(_seam().settings.get("LLM.PLATFORM_DAILY_TOKEN_CAP", 0) or 0)
    if day_cap <= 0:
        return
    day_used = await get_platform_day_used()
    if day_used is None:
        if bool(_seam().settings.get("LLM.BUDGET_FAIL_CLOSED", False)):
            logger.error("平台当日 LLM 用量读数不可用，fail-closed 拒绝")
            raise BusinessException(
                "LLM token 预算读数不可用（Redis），fail-closed 拒绝调用: platform-day",
                code="LLM_BUDGET_UNAVAILABLE", status_code=503,
            )
    elif day_used >= day_cap:
        logger.warning(f"平台今日 LLM 额度已用完 | used={day_used} cap={day_cap}")
        raise BusinessException(
            "平台今日 AI 额度已用完，请明天再试（或在「模型配置」接入自有模型）。",
            code="LLM_PLATFORM_DAILY_CAP", status_code=429,
        )


async def _account_usage(dim: str, budget: int, model: str, tenant_id, norm: dict[str, int]) -> None:
    """用量记账（total 为 0 不记）：进程内存累计（熔断）+ P0-3 持久化
    （Redis 日/月计数；内部失败不影响主路径；测试态为 no-op，保持纯内存语义）"""
    used = norm["total"]
    if not used:
        return
    _seam()._TOKEN_USAGE[dim] = _seam()._TOKEN_USAGE.get(dim, 0) + used
    logger.info(
        f"LLM token 用量: +{used}（{dim} 累计 "
        f"{_seam()._TOKEN_USAGE[dim]}/{budget}）"
    )
    await record_usage(
        dim=dim, model=model, tenant_id=tenant_id,
        prompt_tokens=norm["prompt"], completion_tokens=norm["completion"],
        total_tokens=used,
    )


def _raise_if_rejected(exc: httpx.HTTPStatusError, provider_id: Optional[int]) -> None:
    """4xx（429 除外）不重试：供应商路径抛结构化供应商错误，其余抛拒绝业务异常"""
    status = exc.response.status_code
    if 400 <= status < 500 and status != 429:
        if provider_id is not None:
            raise _provider_error(exc)
        raise BusinessException(f"LLM 请求被拒绝（HTTP {status}），不重试: {exc}")


async def _retry_backoff(label: str, attempt: int, max_retries: int, last_error) -> None:
    """指数退避（_RETRY_BASE_DELAY × 2^attempt）并记重试告警"""
    delay = _RETRY_BASE_DELAY * (2 ** attempt)
    logger.warning(
        f"{label}（第 {attempt + 1}/{max_retries} 次），"
        f"{delay:.1f}s 后重试: {last_error}"
    )
    await asyncio.sleep(delay)


async def _llm_chat_gateway(
    messages: list[dict],
    cfg: LlmRuntimeConfig,
    *,
    usage_dim: Optional[str],
    budget_override: Optional[int],
    model_override: Optional[str],
) -> str:
    """平台路径：只经 llm_gateway.chat POST /v1/chat/completions。"""
    logger.info("平台网关 llm_chat")
    if not cfg.base_url:
        raise _gateway_unreachable(None)
    models = await _probe_gateway_models(cfg.timeout)
    model = model_override or (cfg.model if cfg.model in models else models[0])
    payload = {"model": model, "messages": messages, "temperature": cfg.temperature}
    budget = _resolve_budget(budget_override)
    dim = usage_dim or "config"
    last_error: Exception | None = None
    from platform_core.tenant_context import current_tenant_id as _cur_tid

    _tid = _cur_tid()
    for attempt in range(cfg.max_retries):
        await _budget_guard(dim, budget, _tid)
        try:
            data = await chat_completions(payload, timeout=cfg.timeout)
            content = _openai_content(data)
            if not content:
                raise ValueError("LLM 响应缺少 content")
            await _account_usage(dim, budget, model, _tid, _normalize_usage("openai_compatible", data))
            return content
        except BusinessException:
            raise
        except httpx.HTTPStatusError as e:
            _raise_if_rejected(e, None)
            last_error = e
        except Exception as e:  # noqa: BLE001 超时/网络/解析失败均进入重试
            last_error = e
        await _retry_backoff("平台网关调用失败", attempt, cfg.max_retries, last_error)
    raise _gateway_unreachable(last_error)


async def _failover(messages, *, usage_dim, budget_override, cfg, primary_error):
    """B-M4-1：主模型耗尽重试后按候选链接管（priority 升序，默认行已由主路径尝试过）；
    strong→basic 跨级降质发告警不静默（审计 10.2-E）；全耗尽抛含各候选摘要的结构化失败"""
    from platform_core.exceptions import BusinessException as _BizErr

    if cfg.provider_id is None:
        raise _BizErr(f"LLM 调用失败（已重试 {cfg.max_retries} 次）: {primary_error}")
    chain = [
        (model_id, tier) for model_id, tier in await _candidate_chain(cfg.provider_id)
        if model_id != cfg.model
    ]
    if not chain:
        raise _provider_error(primary_error)

    # 当前模型 tier（默认行；缺省按 basic 保守处理，跨级判定宁缺勿滥告警）
    current_tier = "basic"
    for model_id, tier in await _candidate_chain(cfg.provider_id):
        if model_id == cfg.model:
            current_tier = tier
            break

    failures: list[str] = [f"{cfg.model}: {type(primary_error).__name__}"]
    for model_id, tier in chain:
        logger.warning(f"LLM 故障转移 | {cfg.model} → {model_id}（tier {current_tier}→{tier}）")
        try:
            content = await llm_chat(
                messages, usage_dim=usage_dim, budget_override=budget_override,
                model_override=model_id, _no_failover=True,
            )
            if current_tier == "strong" and tier == "basic":
                await _notify_degrade(cfg, model_id)
            return content
        except Exception as exc:  # noqa: BLE001 单候选失败继续下一候选
            failures.append(f"{model_id}: {type(exc).__name__}")
            from backend.services.ai_planner._cooldown import record_failure as _rec_fail

            await _rec_fail(cfg.provider_id, model_id)
    logger.warning(f"本企业供应商候选链耗尽 | n={len(failures)}")
    raise _provider_error(primary_error)


# ----------------------------------------------------------------------
# 直连路径（激活供应商 / yml+env 兜底）
# ----------------------------------------------------------------------
async def _post_direct(cfg: LlmRuntimeConfig, call: _DirectCall) -> dict:
    """直连出站：provider 路径走共享 client，兜底路径每调用一次性 client"""
    if cfg.provider_id is not None:
        # provider 路径：模块级共享 client（连接池复用，变更时 invalidate 失效）
        client = await _seam().get_shared_client(
            cfg.base_url, cfg.api_key, cfg.timeout, cfg.provider_id
        )
        resp = await client.post(call.url, json=call.payload, headers=call.headers)
        resp.raise_for_status()
    else:
        # 兜底路径：与现状完全一致（每调用一次性 client，yml/env 配置）；
        # trust_env=False 不走系统代理（本机代理劫持陷阱，同 provider 路径约定）
        async with httpx.AsyncClient(timeout=cfg.timeout, trust_env=False) as client:
            resp = await client.post(call.url, json=call.payload, headers=call.headers)
            resp.raise_for_status()
    return resp.json()


async def _direct_once(cfg: LlmRuntimeConfig, call: _DirectCall) -> str:
    """直连单次尝试：出站 → 解析 content → 记账（异常交由重试循环分类）"""
    data = await _post_direct(cfg, call)
    if call.adapter is None:
        content = _openai_content(data)
    else:
        content = call.adapter.parse_chat(data)
    if not content:
        raise ValueError("LLM 响应缺少 content")
    await _account_usage(
        call.usage_dim, call.budget, call.model, call.tenant_id,
        _normalize_usage(call.protocol, data),
    )
    return content


async def _direct_attempts(
    cfg: LlmRuntimeConfig, call: _DirectCall,
) -> tuple[Optional[str], Optional[Exception]]:
    """直连重试循环：成功返回 (content, None)；重试耗尽返回 (None, 最后一次异常)"""
    last_error: Exception | None = None
    for attempt in range(cfg.max_retries):
        # 平台预算闸（与网关路径同一实现）；企业月度 token 套餐闸已在出站前由
        # _enforce_tenant_token_quota 按上海自然月执行一次（原此处重复的本地日期月度闸
        # 口径不一致且吞掉基础设施异常，已删除——审计 R2-10）
        await _budget_guard(call.usage_dim, call.budget, call.tenant_id)
        try:
            return await _direct_once(cfg, call), None
        except BusinessException:
            raise
        except httpx.HTTPStatusError as e:
            _raise_if_rejected(e, cfg.provider_id)
            last_error = e
        except Exception as e:  # noqa: BLE001 超时/网络/解析失败均进入重试
            last_error = e
            if cfg.provider_id and call.model:
                from backend.services.ai_planner._cooldown import record_failure as _rec_fail

                await _rec_fail(cfg.provider_id, call.model)
        await _retry_backoff("LLM 调用失败", attempt, cfg.max_retries, last_error)
    return None, last_error


async def _llm_chat_direct(
    messages: list[dict],
    cfg: LlmRuntimeConfig,
    *,
    usage_dim: Optional[str],
    budget_override: Optional[int],
    model_override: Optional[str],
    no_failover: bool,
) -> str:
    """直连路径：重试循环 → 耗尽后按候选链故障转移（no_failover 时直接抛结构化失败）"""
    call = _prepare_direct_call(messages, cfg, usage_dim, budget_override, model_override)
    content, last_error = await _direct_attempts(cfg, call)
    if content is not None:
        return content
    if not no_failover:
        return await _failover(messages, usage_dim=call.usage_dim, budget_override=budget_override,
                               cfg=cfg, primary_error=last_error)
    if cfg.provider_id is not None:
        raise _provider_error(last_error)
    raise BusinessException(f"LLM 调用失败（已重试 {cfg.max_retries} 次）: {last_error}")


async def llm_chat(
    messages: list[dict],
    *,
    usage_dim: Optional[str] = None,
    budget_override: Optional[int] = None,
    model_override: Optional[str] = None,
    _no_failover: bool = False,
) -> str:
    """chat completions：超时 / 指数退避重试 / token 预算熔断 / 未启用抛业务异常

    原 AiPlannerService._llm_chat 方法体（拆分后委托调用，默认行为零变化）。
    配置来源：激活且 enabled 的供应商优先（provider 路径，共享 client），
    否则 yml/env 兜底（行为与阶段一完全一致，一次性 client）。

    可选参数（A-P2-1 技能评分等旁路消费方使用；不传时行为与拆分前完全一致）：
    - usage_dim：计量维度覆盖（如 "skill_scoring"）——旁路用量与 AI 规划互不挤占；
    - budget_override：该维度独立预算（如 SKILLS.SCORING.MAX_TOKENS_BUDGET），
      替代全局 LLM.MAX_TOKENS_BUDGET 的熔断阈值。
    """
    logger.info("LLM chat 调用入口")
    cfg = await _seam()._resolve_llm_runtime_config()
    # ENABLED=false 须在网关探测前返回，避免与 74.1「平台 LLM 网关不可达」混句
    if not cfg.enabled:
        raise BusinessException(PLANNING_DISABLED_COPY, code=PLANNING_DISABLED_CODE, status_code=422)
    if _is_litellm_plane() and cfg.source == "gateway":
        await _enforce_tenant_token_quota()
        return await _llm_chat_gateway(
            messages, cfg, usage_dim=usage_dim,
            budget_override=budget_override, model_override=model_override,
        )
    _assert_direct_config(cfg)
    # FR-12：套餐闸接到真正打模型的成功路径前、出站 HTTP 前（不切 LiteLLM）
    await _enforce_tenant_token_quota()
    return await _llm_chat_direct(
        messages, cfg, usage_dim=usage_dim, budget_override=budget_override,
        model_override=model_override, no_failover=_no_failover,
    )
