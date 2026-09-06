"""spider_results 按租户套餐天数归档后物理删除。"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from platform_core.db import get_manager
from platform_core.logger import get_logger
from platform_core.models.archive import ArchiveRecord
from platform_core.models.spider_result import SpiderResult
from platform_core.models.tenant import Tenant
from backend.services.quota_service import quota_of

logger = get_logger("service.retention")

_DEFAULT_DAYS = 90
_BATCH = 200


class RetentionService:
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if "pytest" in sys.modules:
            logger.info("retention 测试态不启动")
            return
        if not settings.get("RETENTION.ENABLED", True):
            logger.info("retention 执行器已禁用")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="retention")
        logger.info("retention 执行器已启动")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        interval = int(settings.get("RETENTION.INTERVAL_SECONDS", 3600) or 3600)
        while self._running:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.warning(f"retention 轮次失败: {e}")
            await asyncio.sleep(max(60, interval))

    async def run_once(self) -> int:
        logger.info("retention 扫描开始")
        engine = get_manager().async_engines.get("DEFAULT")
        if engine is None:
            return 0
        total = 0
        async with AsyncSession(engine) as session:
            tenants = (await session.execute(select(Tenant))).scalars().all()
            for tenant in tenants:
                quota = quota_of(tenant)
                days = int(quota.get("result_retention_days") or _DEFAULT_DAYS)
                cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                ids = (await session.execute(
                    select(SpiderResult.id, SpiderResult.tenant_id, SpiderResult.task_id,
                           SpiderResult.spider_name, SpiderResult.url, SpiderResult.title)
                    .where(
                        SpiderResult.tenant_id == tenant.id,
                        SpiderResult.created_at < cutoff,
                    ).limit(_BATCH)
                )).all()
                for row in ids:
                    session.add(ArchiveRecord(
                        tenant_id=row.tenant_id,
                        source_table="spider_results",
                        source_id=row.id,
                        snapshot={
                            "task_id": row.task_id,
                            "spider_name": row.spider_name,
                            "url": row.url,
                            "title": row.title,
                        },
                        retention_until=datetime.now(timezone.utc) + timedelta(days=180),
                    ))
                    await session.execute(delete(SpiderResult).where(SpiderResult.id == row.id))
                    total += 1
            await session.commit()
        logger.info(f"retention 完成 | archived={total}")
        return total
