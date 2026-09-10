"""租户到期巡检（SaaS S5-2）——expires_at 过期 → status=expired（登录被拒可行动文案）"""
import asyncio
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.db import get_manager
from platform_core.exceptions import AuthenticationException
from platform_core.logger import get_logger
from platform_core.models.tenant import Tenant

logger = get_logger("service.tenant_expiry")

# FR-08 / GWT-08.1：内部码不得渲染成密码错误；用户可见句与凭证失败不是同一句
AUTH_TENANT_EXPIRED = "AUTH_TENANT_EXPIRED"
TENANT_EXPIRED_MESSAGE = "企业已到期或停用，请联系平台"
_INACTIVE_STATUSES = frozenset({"expired", "disabled"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# 到期/停用企业拒绝登录颁发与后续写（FR-08）。平台超管跳过。
async def assert_tenant_active(session: AsyncSession, tenant_id: int | None, *, is_platform_admin: bool = False) -> None:
    logger.info(f"租户可用性检查 | tenant_id={tenant_id} platform={is_platform_admin}")
    if is_platform_admin or tenant_id is None:
        return
    tenant = await session.get(Tenant, int(tenant_id))
    status = getattr(tenant, "status", None) if tenant is not None else None
    if tenant is None or status in _INACTIVE_STATUSES:
        logger.warning(f"拒绝到期或停用租户 | tenant_id={tenant_id} status={status}")
        raise AuthenticationException(
            message=TENANT_EXPIRED_MESSAGE, code=AUTH_TENANT_EXPIRED
        )


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
