"""中转 SKU 读闸（FR-U20…U23 / ADR-0025）。

已买真相只在 relay_sku_entitlements：缺行 ≡ none。禁止用组行数量当已买。
本模块只读权益表；开通写入在 PaymentNotifyService（商品=relay）。专业档履约不得经本模块写权益。
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.relay_sku_entitlement_repository import (
    RelaySkuEntitlementRepository,
)
from backend.services.quota_service import resolve_upgrade_intent
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger
from platform_core.schemas.relay import RelaySkuPageOut, RelayUpgradeOut

logger = get_logger("service.relay_sku")

MSG_SKU_NONE = "未开通中转"
MSG_SKU_NONE_HINT = "开通后才能查看本企业用量并签发令牌。"
MSG_SKU_EXPIRED = "中转已到期"
MSG_SKU_EXPIRED_HINT = "到期后不能签发新令牌，已签发的令牌也不能再用。"
MSG_UPGRADE = "去升级"
RELAY_SKU_INACTIVE = "RELAY_SKU_INACTIVE"
RELAY_PRODUCT = "relay"
_VALID = frozenset({"none", "active", "expired"})


def empty_title(status: str) -> str:
    logger.debug(f"SKU 空态标题 | status={status}")
    return MSG_SKU_EXPIRED if status == "expired" else MSG_SKU_NONE


def empty_hint(status: str) -> str:
    logger.debug(f"SKU 空态说明 | status={status}")
    return MSG_SKU_EXPIRED_HINT if status == "expired" else MSG_SKU_NONE_HINT


def raise_missing() -> None:
    """跨租户 / 凭证不可用：与页面不存在同形（HTTP_404 / Not Found）。"""
    logger.debug("渠道组资源 404 同形")
    raise BusinessException(message="Not Found", code="HTTP_404", status_code=404)


def raise_sku_inactive(status: str) -> None:
    logger.info(f"SKU 非 active 拒绝写 | status={status}")
    raise BusinessException(
        message=empty_title(status),
        code=RELAY_SKU_INACTIVE,
        status_code=422,
    )


def relay_upgrade(tenant_role: Optional[str]) -> RelayUpgradeOut:
    """买方去升级 product=relay；经办/只读联系管理员、不建单。"""
    logger.info(f"中转去升级意图 | role={tenant_role}")
    raw = resolve_upgrade_intent(tenant_role, RELAY_PRODUCT)
    message = MSG_UPGRADE if raw["action"] == "checkout" else str(raw["message"])
    return RelayUpgradeOut(
        action=str(raw["action"]),
        product=RELAY_PRODUCT,
        checkout_path=raw.get("checkout_path"),
        message=message,
    )


async def load_sku_status(session: AsyncSession, tenant_id: int) -> str:
    """点查权益。缺行 ≡ none。不读组行、不 COUNT。"""
    logger.info(f"读中转 SKU 权益 | tenant={tenant_id}")
    row = await RelaySkuEntitlementRepository(session).get_by_tenant_id(tenant_id)
    if row is None:
        return "none"
    status = str(row.status or "none")
    return status if status in _VALID else "none"


async def load_sku_period_end(
    session: AsyncSession, tenant_id: int,
) -> Optional[datetime]:
    logger.debug(f"读中转账期 | tenant={tenant_id}")
    row = await RelaySkuEntitlementRepository(session).get_by_tenant_id(tenant_id)
    return None if row is None else row.period_end


async def require_active_sku(session: AsyncSession, tenant_id: int) -> None:
    logger.info(f"要求中转 SKU active | tenant={tenant_id}")
    status = await load_sku_status(session, tenant_id)
    if status != "active":
        raise_sku_inactive(status)


async def sku_page(
    session: AsyncSession, tenant_id: int, tenant_role: Optional[str],
    *, can_issue: bool,
) -> RelaySkuPageOut:
    logger.info(f"组装我的渠道组 SKU 页 | tenant={tenant_id} role={tenant_role}")
    status = await load_sku_status(session, tenant_id)
    period_end = await load_sku_period_end(session, tenant_id)
    active = status == "active"
    upgrade = None if active else relay_upgrade(tenant_role)
    return RelaySkuPageOut(
        status=status,
        period_end=period_end,
        can_issue=bool(active and can_issue),
        empty_title="" if active else empty_title(status),
        empty_hint="" if active else empty_hint(status),
        upgrade=upgrade,
    )
