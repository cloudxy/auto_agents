"""T-18 测试夹具：直接 INSERT 权益行（不走履约/支付宝）。"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from platform_core.models.relay_sku_entitlement import RelaySkuEntitlement


def seed_relay_sku(
    db_session, tenant_id: int, status: str = "active",
    period_end: Optional[datetime] = None,
) -> None:
    async def _go():
        async with db_session() as s:
            row = (await s.execute(
                select(RelaySkuEntitlement).where(
                    RelaySkuEntitlement.tenant_id == tenant_id,
                )
            )).scalar_one_or_none()
            if row is None:
                s.add(RelaySkuEntitlement(
                    tenant_id=tenant_id, status=status, period_end=period_end,
                ))
            else:
                row.status = status
                row.period_end = period_end
            await s.commit()

    asyncio.run(_go())
