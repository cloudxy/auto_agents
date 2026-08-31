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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from platform_core.logger import get_logger

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


def create_app():
    """创建 FastAPI 应用实例（不含初始化逻辑）"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """应用生命周期：密钥守卫 + Redis 队列消费者 + 定时调度器 + 代理健康管理 + LLM 用量聚合"""
        _validate_runtime_secrets()
        consumer = None
        if settings.get("TASKS.CONSUMER_ENABLED", True):
            from backend.tasks.consumer import SpiderTaskConsumer

            consumer = SpiderTaskConsumer()
            try:
                await consumer.start()
            except Exception as e:  # noqa: BLE001 失败仅告警，不阻断应用启动
                get_logger("global").warning(f"Redis 队列消费者启动失败（忽略）: {e}")
        scheduler = None
        if settings.get("SCHEDULER.ENABLED", True):
            from backend.services.schedule_service import SpiderScheduler

            scheduler = SpiderScheduler()
            try:
                await scheduler.start()
            except Exception as e:  # noqa: BLE001 失败仅告警，不阻断应用启动
                get_logger("global").warning(f"爬虫调度器启动失败（忽略）: {e}")
        proxy_health = None
        if settings.get("PROXY_HEALTH.ENABLED", False):
            from backend.services.proxy_health_service import ProxyHealthService

            proxy_health = ProxyHealthService()
            try:
                await proxy_health.start()
            except Exception as e:  # noqa: BLE001 失败仅告警，不阻断应用启动
                get_logger("global").warning(f"代理健康管理启动失败（忽略）: {e}")
        # LLM 用量聚合落库（P0-3）：Redis 日粒度计数 → llm_token_usage 表
        llm_usage_flush = None
        if settings.get("LLM.USAGE_PERSIST_ENABLED", True):
            from backend.services.llm_usage_service import LlmUsageFlushService

            llm_usage_flush = LlmUsageFlushService()
            try:
                await llm_usage_flush.start()
            except Exception as e:  # noqa: BLE001 失败仅告警不阻断启动
                get_logger("global").warning(f"LLM 用量聚合任务启动失败（忽略）: {e}")
        # new-api 渠道集成（阶段三）：三层开关 ENABLED → SCHEDULER_ENABLED / PROBE_ENABLED，
        # 失败仅告警不阻断启动（外部系统依赖故障不影响主平台可用性）
        newapi_scheduler = None
        newapi_probe = None
        if settings.get("NEWAPI.ENABLED", False):
            if settings.get("NEWAPI.SCHEDULER_ENABLED", False):
                from backend.services.channel_scheduler_service import ChannelSchedulerService

                newapi_scheduler = ChannelSchedulerService()
                try:
                    await newapi_scheduler.start()
                except Exception as e:  # noqa: BLE001 失败仅告警，不阻断应用启动
                    get_logger("global").warning(f"渠道调度器启动失败（忽略）: {e}")
            if settings.get("NEWAPI.PROBE_ENABLED", False):
                from backend.services.channel_probe_service import ChannelProbeService

                newapi_probe = ChannelProbeService()
                try:
                    await newapi_probe.start()
                except Exception as e:  # noqa: BLE001 失败仅告警，不阻断应用启动
                    get_logger("global").warning(f"渠道探针启动失败（忽略）: {e}")
        # 启动对账：进程中断遗留的 planning/testing AI 计划置 failed（失败不阻断启动）
        try:
            from backend.services.ai_planner_service import reconcile_interrupted_plans

            recovered = await reconcile_interrupted_plans()
            if recovered:
                get_logger("global").info(f"启动对账完成：恢复 {recovered} 个中断的 AI 计划")
        except Exception as e:  # noqa: BLE001 对账失败仅告警，不阻断应用启动
            get_logger("global").warning(f"AI 计划启动对账失败（忽略）: {e}")
        yield
        # 关闭链（评审 L1）：各 stop() 独立 try/except，单一组件关闭失败
        # 不阻断其余组件的停止（避免残留后台任务/连接泄漏）
        if newapi_probe is not None:
            try:
                await newapi_probe.stop()
            except Exception as e:  # noqa: BLE001 关闭失败仅告警，继续关闭其余组件
                get_logger("global").warning(f"渠道探针停止失败（忽略）: {e}")
        if newapi_scheduler is not None:
            try:
                await newapi_scheduler.stop()
            except Exception as e:  # noqa: BLE001 关闭失败仅告警，继续关闭其余组件
                get_logger("global").warning(f"渠道调度器停止失败（忽略）: {e}")
        if proxy_health is not None:
            try:
                await proxy_health.stop()
            except Exception as e:  # noqa: BLE001 关闭失败仅告警，继续关闭其余组件
                get_logger("global").warning(f"代理健康管理停止失败（忽略）: {e}")
        if scheduler is not None:
            try:
                await scheduler.stop()
            except Exception as e:  # noqa: BLE001 关闭失败仅告警，继续关闭其余组件
                get_logger("global").warning(f"爬虫调度器停止失败（忽略）: {e}")
        if consumer is not None:
            try:
                await consumer.stop()
            except Exception as e:  # noqa: BLE001
                get_logger("global").warning(f"Redis 队列消费者停止失败（忽略）: {e}")
        if llm_usage_flush is not None:
            try:
                await llm_usage_flush.stop()
            except Exception as e:  # noqa: BLE001
                get_logger("global").warning(f"LLM 用量聚合任务停止失败（忽略）: {e}")
        if skill_scoring_worker is not None:
            try:
                await skill_scoring_worker.stop()
            except Exception as e:  # noqa: BLE001
                get_logger("global").warning(f"技能评分 worker 停止失败（忽略）: {e}")

    app = FastAPI(
        title="Auto Agents API",
        description="自动化代理系统 API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS 配置（从 web.yml 配置文件读取）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS.ORIGINS,
        allow_credentials=settings.CORS.ALLOW_CREDENTIALS,
        allow_methods=settings.CORS.ALLOW_METHODS,
        allow_headers=settings.CORS.ALLOW_HEADERS,
    )

    # 请求 ID 中间件（链路追踪）
    from backend.app.middleware import RequestIDMiddleware
    app.add_middleware(RequestIDMiddleware)

    # 注册统一异常处理器
    from platform_core.exceptions import register_exception_handlers
    register_exception_handlers(app)

    # 注册内部 API 路由（用于管理后台、前端、内部服务）
    from backend.app.api import api_router
    app.include_router(api_router, prefix="/api")

    # 注册外部 API 路由（用于第三方集成、开放平台、Webhook）
    from backend.app.external_api import external_api_router
    app.include_router(external_api_router, prefix="/external")
    
    return app

app = create_app()