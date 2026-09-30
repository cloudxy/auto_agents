"""企业可用性检查（FR-08）：停用 / 人工置为到期的企业拒绝登录与后续请求。

账期到期不再停用企业（决策 D22）：由 subscription_lifecycle 提醒、宽限后降为免费档。
原「到期即置 expired」巡检已删除——它从没接进启动流程，接上又会把企业整体锁死、连续费页都进不去。
"""
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.exceptions import AuthenticationException
from platform_core.logger import get_logger
from platform_core.models.tenant import Tenant

logger = get_logger("service.tenant_expiry")

# FR-08 / GWT-08.1：内部码不得渲染成密码错误；用户可见句与凭证失败不是同一句
AUTH_TENANT_EXPIRED = "AUTH_TENANT_EXPIRED"
TENANT_EXPIRED_MESSAGE = "企业已到期或停用，请联系平台"
_INACTIVE_STATUSES = frozenset({"expired", "disabled"})


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
