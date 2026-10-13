"""
FastAPI 应用核心模块 - 应用级初始化和全局配置

职责：
- 创建 FastAPI 实例
- 配置全局中间件（CORS等）
- 注册 API 路由（不关心具体业务实现）
- lifespan 内启动 Redis 队列消费者（数据闭环引擎，可用 TASKS.CONSUMER_ENABLED 关闭）

注意：
- 不包含任何业务逻辑
- 不直接定义路由
- 通过 app/api/ 聚合器注册路由
- 初始化逻辑已移至 cors/app_init.py
- lifespan 内各后台组件启动/停止失败均仅告警不互相阻断（评审 H4/L1：
  单一组件故障不影响应用可用性与其余组件的启停）
"""
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib import import_module

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from backend.config_consts import (RELAY_PROBE_ENABLED, RELAY_SCHEDULER_ENABLED)
from platform_core.logger import get_logger

def _install_utc_json_encoder() -> None:
    """dict 出参里的 datetime 也带 +00:00（审计 BUG-43）。

    schema 出参由 UTCDateTime 负责；没有 response_model、直接返回 dict 的接口走
    jsonable_encoder，其按类型查 ENCODERS_BY_TYPE。库里是 UTC naive，默认 isoformat
    不带偏移，前端 new Date() 会按浏览器本地时区解释、差 8 小时。只作用于 datetime
    对象，不碰字符串（采集结果里的原文时间串原样返回）。
    """
    from datetime import datetime

    from fastapi import encoders

    from platform_core.timeutil import utc_iso

    encoders.ENCODERS_BY_TYPE[datetime] = utc_iso


_install_utc_json_encoder()

# Webhook 签名密钥的默认占位符（config/default/webhook.yml）——已随仓库公开，
# 沿用即意味着外部回调可被任意伪造，启动时必须拒绝（P0-2）
_WEBHOOK_SECRET_PLACEHOLDER = "change-me-in-production"


def _validate_runtime_secrets() -> None:
    """启动期密钥 fail-fast（P0-2）：Webhook 密钥为空/默认占位符时拒绝启动

    与 JWT 守卫（backend/utils/auth.py 对同款占位符导入即抛错）构成对称防线；
    Scrapy 侧 SpiderCloseWebhook 读取同一配置源（config/default/webhook.yml），
    两侧密钥必须一致，配置入口：config/<env>/.env 的 AUTO_AGENTS_WEBHOOK__SECRET_KEY。
    """
    secret = str(settings.get("WEBHOOK.SECRET_KEY", "") or "").strip()
    if not secret or secret == _WEBHOOK_SECRET_PLACEHOLDER:
        raise RuntimeError(
            "WEBHOOK.SECRET_KEY 未配置或仍为默认占位符，拒绝启动（外部回调可被伪造）。"
            "请在 config/<env>/.env 配置 AUTO_AGENTS_WEBHOOK__SECRET_KEY"
            "（Backend 与 Scrapy 两侧一致），"
            "生成命令：python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )

    # B1（工单 76）：LLM 主密钥占位符/格式 fail-fast——密钥已配置但为占位符或非法
    # Fernet 格式时拒绝启动（否则保存的 api_key 密文将不可解）；
    # 空值 = yml/env 兜底模式（不落库加密），放行
    import os as _os

    llm_key = str(
        _os.environ.get("LLM_ENCRYPTION_KEY")
        or settings.get("LLM_ENCRYPTION_KEY", "")
        or ""
    ).strip()
    if llm_key == _WEBHOOK_SECRET_PLACEHOLDER:
        raise RuntimeError(
            "LLM_ENCRYPTION_KEY 仍为默认占位符，拒绝启动。"
            "生成命令：python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    if llm_key:
        try:
            from cryptography.fernet import Fernet as _F

            _F(llm_key.encode("utf-8"))
        except Exception as exc:  # noqa: BLE001 任何格式错误均属启动期拒绝范围
            raise RuntimeError(f"LLM_ENCRYPTION_KEY 非法 Fernet 密钥，拒绝启动: {exc}")


def _validate_enablement_duty_contact() -> None:
    """LLM/能力市场启用前必须有 OPS.DUTY_CONTACT；不代填号码（Q-OPS-DUTY 仍开放）。"""
    llm_on = bool(settings.get("LLM.ENABLED", False))
    market_on = bool(settings.get("POWER_MARKET.ENABLED", False))
    if not llm_on and not market_on:
        return
    contact = str(settings.get("OPS.DUTY_CONTACT", "") or "").strip()
    if contact:
        return
    raise RuntimeError(
        "LLM.ENABLED 或 POWER_MARKET.ENABLED 已打开，但 OPS.DUTY_CONTACT 为空，拒绝启动。"
        "请填写值班联系方式后再启用（不代填号码；Q-OPS-DUTY 仍由操作者指定）。"
        "配置键：OPS.DUTY_CONTACT / AUTO_AGENTS_OPS__DUTY_CONTACT"
    )


@dataclass(frozen=True)
class _BackgroundComponent:
    """lifespan 后台组件登记项（类按 module.cls 延迟导入，开关关闭时不导入）

    switch 为 None = 后台角色下常开（组件 start() 内自行判断是否跳过）；
    label 为告警文案主语，按原文拼出「<label>启动失败/停止失败（忽略）」。
    """

    name: str
    module: str
    cls: str
    label: str
    switch: str | None = None
    default: bool = True


# 启动顺序 = 登记顺序；仅 APP_ROLE ∈ {all, worker} 时启动
_BACKGROUND_COMPONENTS = (
    _BackgroundComponent("consumer", "backend.tasks.consumer", "SpiderTaskConsumer",
                         "Redis 队列消费者", "TASKS.CONSUMER_ENABLED", True),
    _BackgroundComponent("scheduler", "backend.services.schedule_service", "SpiderScheduler",
                         "爬虫调度器", "SCHEDULER.ENABLED", True),
    _BackgroundComponent("proxy_health", "backend.services.proxy_health_service",
                         "ProxyHealthService", "代理健康管理", "PROXY_HEALTH.ENABLED", False),
    # LLM 用量聚合落库（P0-3）：Redis 日粒度计数 → llm_token_usage 表
    _BackgroundComponent("llm_usage_flush", "backend.services.llm_usage_service",
                         "LlmUsageFlushService", "LLM 用量聚合任务",
                         "LLM.USAGE_PERSIST_ENABLED", True),
    # 技能 AI 评分 worker（方案 A · A-P2-2）：SKILLS.SCORING.ENABLED 控制，
    # 失败仅告警不阻断启动（评分队列积压可在恢复后继续消费）
    _BackgroundComponent("skill_scoring_worker", "backend.services.skill_scoring_service",
                         "SkillScoringWorker", "技能评分 worker ", "SKILLS.SCORING.ENABLED", False),
    # LLM 周期健康巡检（方案 B · B-M4-2）：LLM.HEALTH_PATROL_ENABLED 控制
    _BackgroundComponent("llm_health_patrol", "backend.services.llm_health_patrol",
                         "LlmHealthPatrol", "LLM 健康巡检", "LLM.HEALTH_PATROL_ENABLED", False),
    # T-20：窗口/探针只读 RELAY.*；失败仅告警不阻断启动
    _BackgroundComponent("newapi_scheduler", "backend.services.channel_scheduler_service",
                         "ChannelSchedulerService", "渠道调度器",
                         "RELAY.SCHEDULER_ENABLED", RELAY_SCHEDULER_ENABLED),
    _BackgroundComponent("newapi_probe", "backend.services.channel_probe_service",
                         "ChannelProbeService", "渠道探针",
                         "RELAY.PROBE_ENABLED", RELAY_PROBE_ENABLED),
    # 中转执法巡检（审计 BUG-28 / D19）：SKU 到期落库 + 令牌网关封禁对齐；
    # 未配置 LiteLLM 网关或 RELAY.ENFORCE_ENABLED=false 时 start() 内自行跳过
    _BackgroundComponent("relay_enforcement", "backend.services.relay_enforcement",
                         "RelayEnforcementService", "中转执法巡检"),
    # 账期巡检（决策 D22 / 审计 B2-1）：到期提醒 → 宽限 → 降免费档（不停用企业）
    _BackgroundComponent("subscription_lifecycle", "backend.services.subscription_lifecycle",
                         "SubscriptionLifecycleService", "账期巡检"),
    _BackgroundComponent("retention", "backend.services.retention_service", "RetentionService",
                         "retention ", "RETENTION.ENABLED", True),
)
_COMPONENT_LABELS = {c.name: c.label for c in _BACKGROUND_COMPONENTS}

# 关闭链顺序（评审 L1）：沿用既有顺序（并非启动逆序）
_SHUTDOWN_ORDER = (
    "subscription_lifecycle", "relay_enforcement", "newapi_probe", "newapi_scheduler",
    "proxy_health", "scheduler", "consumer", "llm_usage_flush", "llm_health_patrol",
    "skill_scoring_worker", "retention",
)
if sorted(_SHUTDOWN_ORDER) != sorted(_COMPONENT_LABELS):  # 不用 assert：python -O 会跳过
    raise RuntimeError("关闭链 _SHUTDOWN_ORDER 须恰好覆盖全部登记的后台组件（不重不漏）")


async def _start_background_components(run_bg: bool) -> dict:
    """按登记顺序启动后台组件，返回 {名称: 实例}

    实例先登记再 start()：启动失败的组件同样进入关闭链（照常 stop）。
    """
    started: dict = {}
    if not run_bg:
        return started
    for spec in _BACKGROUND_COMPONENTS:
        if spec.switch is not None and not settings.get(spec.switch, spec.default):
            continue
        component = getattr(import_module(spec.module), spec.cls)()
        started[spec.name] = component
        try:
            await component.start()
        except Exception as e:  # noqa: BLE001 失败仅告警，不阻断应用启动
            get_logger("global").warning(f"{spec.label}启动失败（忽略）: {e}")
    return started


async def _reconcile_interrupted_plans() -> None:
    """启动对账：进程中断遗留的 planning/testing AI 计划置 failed（失败不阻断启动）"""
    try:
        from backend.services.ai_planner_service import reconcile_interrupted_plans

        recovered = await reconcile_interrupted_plans()
        if recovered:
            get_logger("global").info(f"启动对账完成：恢复 {recovered} 个中断的 AI 计划")
    except Exception as e:  # noqa: BLE001 对账失败仅告警，不阻断应用启动
        get_logger("global").warning(f"AI 计划启动对账失败（忽略）: {e}")


async def _stop_background_components(started: dict) -> None:
    """关闭链（评审 L1）：各 stop() 独立 try/except，单一组件关闭失败
    不阻断其余组件的停止（避免残留后台任务/连接泄漏）
    """
    for name in _SHUTDOWN_ORDER:
        if name not in started:
            continue
        try:
            await started[name].stop()
        except Exception as e:  # noqa: BLE001 关闭失败仅告警，继续关闭其余组件
            get_logger("global").warning(f"{_COMPONENT_LABELS[name]}停止失败（忽略）: {e}")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """应用生命周期：密钥守卫 + Redis 队列消费者 + 定时调度器 + 代理健康管理 + LLM 用量聚合"""
    _validate_runtime_secrets()
    _validate_enablement_duty_contact()
    from backend.app.cors_check import warn_cors_config
    warn_cors_config(settings)
    import os as _os
    _run_bg = (_os.environ.get("APP_ROLE") or "all").strip().lower() in ("all", "worker")
    components = await _start_background_components(_run_bg)
    await _reconcile_interrupted_plans()
    yield
    await _stop_background_components(components)


def _add_middlewares(app: FastAPI) -> None:
    """全局中间件（注册顺序即既定顺序：CORS → RequestID → TenantContext，勿调换）"""
    from backend.app.cors_check import as_str_list

    # CORS 配置（web.yml / 环境变量；列表键经 as_str_list 归一，与启动自检同口径）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=as_str_list(settings.get("CORS.ORIGINS")),
        allow_credentials=bool(settings.get("CORS.ALLOW_CREDENTIALS", False)),
        allow_methods=as_str_list(settings.get("CORS.ALLOW_METHODS")) or ["GET"],
        allow_headers=as_str_list(settings.get("CORS.ALLOW_HEADERS")),
    )

    # 请求 ID 中间件（链路追踪）
    from backend.app.middleware import RequestIDMiddleware
    app.add_middleware(RequestIDMiddleware)
    # S1-3：租户上下文中间件（JWT 身份 → tenant_scope/platform_scope，行级隔离据此生效）
    from backend.app.middleware.tenant_context import TenantContextMiddleware
    app.add_middleware(TenantContextMiddleware)


def _include_routers(app: FastAPI) -> None:
    """路由注册（内部 API 先于外部 API）"""
    # 注册内部 API 路由（用于管理后台、前端、内部服务）
    from backend.app.api import api_router
    app.include_router(api_router, prefix="/api")

    # 注册外部 API 路由（用于第三方集成、开放平台、Webhook）
    from backend.app.external_api import external_api_router
    app.include_router(external_api_router, prefix="/external")


def create_app():
    """创建 FastAPI 应用实例（不含初始化逻辑）"""
    # T8：业务豁免表注册（唯一事实源 backend/app/tenant_isolation.py；
    # 移除即豁免失效，R13 同步校验会拦截）
    from backend.app.tenant_isolation import setup_tenant_isolation
    setup_tenant_isolation()

    app = FastAPI(
        title="Auto Agents API",
        description="自动化代理系统 API",
        version="1.0.0",
        lifespan=_lifespan,
    )
    _add_middlewares(app)

    # 注册统一异常处理器
    from platform_core.exceptions import register_exception_handlers
    register_exception_handlers(app)

    _include_routers(app)
    return app

app = create_app()
