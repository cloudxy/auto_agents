"""收款通道凭据仓储。平台表，无 tenant_id。"""
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.payment_channel_credential import PaymentChannelCredential
from platform_core.repository import BaseRepository

_CHANNELS = ("alipay", "wechat")


class PaymentChannelCredentialRepository(BaseRepository[PaymentChannelCredential]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=PaymentChannelCredential, session=session)

    async def get_by_channel(self, channel: str) -> Optional[PaymentChannelCredential]:
        stmt = select(PaymentChannelCredential).where(
            PaymentChannelCredential.channel == channel,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_all(self) -> list[PaymentChannelCredential]:
        stmt = select(PaymentChannelCredential).order_by(
            PaymentChannelCredential.channel.asc(),
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def configured_channels(self) -> set[str]:
        rows = await self.list_all()
        return {str(row.channel) for row in rows if row.channel in _CHANNELS}

    async def delete_by_channel(self, channel: str) -> int:
        stmt = delete(PaymentChannelCredential).where(
            PaymentChannelCredential.channel == channel,
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)
