"""租户到期巡检（SaaS S5-2）——expires_at 过期 → status=expired（登录被拒可行动文案）"""
import asyncio
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.db import get_manager
from platform_core.logger import get_logger
from platform_core.models.tenant import Tenant

logger = get_logger("service.tenant_expiry")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# 把 expires_at < now 且 status=active 的租户置 expired；返回处理行数
async def expire_overdue_tenants(session: AsyncSession) -> int:
    logger.info("租户到期巡检执行")
    result = await session.execute(
        update(Tenant)
        .where(
            Tenant.expires_at.isnot(None),
            Tenant.expires_at < _utcnow(),
            Tenant.status == "active",
        )
        .values(status="expired")
        .execution_options(synchronize_session=False)
    )
    count = int(result.rowcount or 0)
    if count:
        logger.warning(f"租户到期降级: {count} 个租户已置 expired")
    return count


class TenantExpiryService:
    """周期巡检组件（lifespan 可选挂载；默认手动/登录时触发）"""

    def __init__(self):
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._running = True
        self._loop_task = asyncio.create_task(self._loop(), name="tenant-expiry")
        logger.info("租户到期巡检已启动")

    async def stop(self) -> None:
        self._running = False
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        logger.info("租户到期巡检已停止")

    async def _loop(self) -> None:
        while self._running:
            try:
                manager = get_manager()
                async with AsyncSession(manager.async_engines["DEFAULT"]) as session:
                    await expire_overdue_tenants(session)
                    await session.commit()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"租户到期巡检异常: {exc}")
            await asyncio.sleep(3600)  # 每小时一轮
