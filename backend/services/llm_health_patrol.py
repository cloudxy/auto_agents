"""LLM 周期健康巡检（方案 B · B-M4-2）

lifespan 常驻组件（第 8 个）：按 LLM.HEALTH_PATROL_INTERVAL_MIN（默认 30min，可配）
批量刷新全部启用供应商 × 启用模型的 health_status（复用 B-M2-2 的 test_model 单模型
逻辑，逐模型 1-token 真测并落库）——同时是故障转移候选链健康位的数据来源。

多实例单跑：llm:patrol:lock 分布式锁（键契约 queues.LLM_PATROL_LOCK）。
fail-closed 说明见 llm_client 预算段（与登录限流 fail-open 方向相反，刻意不对称）。
"""
import asyncio
from typing import Callable, Optional

from sqlalchemy import select

from platform_core.logger import get_logger
from platform_core.models.llm_provider import LlmProvider
from platform_core.models.llm_provider_model import LlmProviderModel
from platform_core.queues import LLM_PATROL_LOCK, distributed_lock
from platform_core.redis_async import get_async_redis

logger = get_logger("service.llm_health_patrol")


class LlmHealthPatrol:
    """周期健康巡检组件（start/stop 与既有常驻组件同范式）"""

    def __init__(self):
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        from config import settings

        if not settings.get("LLM.HEALTH_PATROL_ENABLED", False):
            logger.info("LLM 健康巡检未启用（LLM.HEALTH_PATROL_ENABLED=false）")
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._patrol_loop(), name="llm-health-patrol")
        logger.info("LLM 健康巡检已启动")

    async def stop(self) -> None:
        self._running = False
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        logger.info("LLM 健康巡检已停止")

    async def _patrol_loop(self) -> None:
        from config import settings

        while self._running:
            try:
                redis = await get_async_redis()
                async with distributed_lock(redis, LLM_PATROL_LOCK, ttl=120) as lock:
                    if lock is None:
                        logger.info("健康巡检锁被其他实例持有，本轮跳过")
                    else:
                        await self.patrol_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 单轮失败不中断循环
                logger.warning(f"LLM 健康巡检异常: {exc}")
            interval_min = max(1, int(settings.get("LLM.HEALTH_PATROL_INTERVAL_MIN", 30) or 30))
            await asyncio.sleep(interval_min * 60)

    @staticmethod
    async def patrol_once(session_factory: Optional[Callable] = None) -> dict:
        """批量巡检一轮：启用供应商 × 启用模型逐个 test_model 落健康态

        session_factory 可注入（测试经 db_session）；缺省独立短事务。
        无密钥供应商跳过外呼（避免批量 401 噪音），计入 skipped_nokey。
        """
        from backend.services.llm_provider_service import LlmProviderService

        logger.info("LLM 健康巡检开始")
        summary = {"providers": 0, "models": 0, "skipped_nokey": 0}

        if session_factory is None:
            from platform_core.db import get_manager
            from sqlalchemy.ext.asyncio import AsyncSession

            def session_factory():  # noqa: E306 与 _consume_loop 同范式
                manager = get_manager()
                return AsyncSession(manager.async_engines["DEFAULT"])

        async def _run(session) -> dict:
            providers = (await session.execute(
                select(LlmProvider).where(LlmProvider.enabled == True)  # noqa: E712
            )).scalars().all()

            tested = 0
            skipped = 0
            provider_count = 0
            for provider in providers:
                if not provider.api_key_encrypted:
                    skipped += 1
                    logger.debug(f"巡检跳过（无密钥）| provider={provider.name}")
                    continue
                provider_count += 1
                svc = LlmProviderService(session)
                models = (await session.execute(
                    select(LlmProviderModel.model_id).where(
                        LlmProviderModel.provider_id == provider.id,
                        LlmProviderModel.enabled == True,  # noqa: E712
                    )
                )).scalars().all()
                for model_id in models:
                    try:
                        await svc.test_model(provider.id, model_id)
                        tested += 1
                    except Exception as exc:  # noqa: BLE001 单模型失败不中断整轮
                        logger.warning(f"巡检单模型失败 | provider={provider.name} model={model_id} err={exc}")
            return {"providers": provider_count, "models": tested, "skipped_nokey": skipped}

        session_ctx = session_factory()
        handled = False
        if hasattr(session_ctx, "__aenter__"):
            async with session_ctx as session:
                summary = await _run(session)
                await session.commit()
            handled = True
        if not handled:
            # 工厂直接返回会话对象（测试注入形态）
            summary = await _run(session_ctx)
            await session_ctx.commit()

        logger.info(f"LLM 健康巡检完成: {summary}")
        return summary
