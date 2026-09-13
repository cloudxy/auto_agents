"""出站拉数钥匙数据访问层（FR-51）。

只碰 outbound_keys 一张表；禁止引用 relay_tokens / KEY_BINDINGS
（查找集合不相交，ADR-0020；拉数执法查找链第一环在 T-05）。
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.outbound_key import OutboundKey
from platform_core.repository import BaseRepository


class OutboundKeyRepository(BaseRepository[OutboundKey]):
    """OutboundKey Repository —— 本企业出站钥匙的读写"""

    def __init__(self, session: AsyncSession):
        super().__init__(model=OutboundKey, session=session)

    async def list_by_tenant(self, tenant_id: int) -> list[OutboundKey]:
        """本企业全部钥匙（含已吊销行——吊销是终态审计，列表要能看见状态）"""
        stmt = (
            select(OutboundKey)
            .where(OutboundKey.tenant_id == tenant_id)
            .order_by(OutboundKey.created_at.desc(), OutboundKey.id.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_by_hash(self, key_hash: str) -> Optional[OutboundKey]:
        """拉数查找链第一环（T-05 / GWT-51.7）：按指纹取 active 行。

        revoked_at 非空即不命中——吊销后同一把钥匙再也拉不到行。
        """
        stmt = select(OutboundKey).where(
            OutboundKey.key_hash == key_hash,
            OutboundKey.revoked_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_owned(self, tenant_id: int, key_id: int) -> Optional[OutboundKey]:
        """按 id 取本企业钥匙；他企业/不存在一律 None（404 同形由 Service 抛）"""
        stmt = select(OutboundKey).where(
            OutboundKey.id == key_id,
            OutboundKey.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
