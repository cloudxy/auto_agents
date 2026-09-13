"""超管商户凭据：Fernet 落库、读回掩码、轮换丢弃旧密文（FR-U31）。"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.payment_channel_credential_repository import (
    PaymentChannelCredentialRepository,
)
from backend.services.llm_secret_vault import LlmSecretVault
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.models.payment_channel_credential import PaymentChannelCredential
from platform_core.schemas.payment_channel_credential import (
    PaymentChannel,
    PaymentChannelCredentialListOut,
    PaymentChannelCredentialPut,
    PaymentChannelCredentialView,
    SECRETS_MASK,
)

logger = get_logger("service.payment_credential")

_CHANNELS: tuple[PaymentChannel, ...] = ("alipay", "wechat")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _empty_view(channel: PaymentChannel) -> PaymentChannelCredentialView:
    return PaymentChannelCredentialView(channel=channel, configured=False)


class PaymentCredentialService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = PaymentChannelCredentialRepository(session)

    async def list_for_admin(self) -> PaymentChannelCredentialListOut:
        logger.info("列出商户凭据（掩码）")
        by_ch = {str(row.channel): row for row in await self.repo.list_all()}
        return PaymentChannelCredentialListOut(
            channels=[self._to_view(ch, by_ch.get(ch)) for ch in _CHANNELS],
        )

    async def put(self, payload: PaymentChannelCredentialPut, actor: str) -> PaymentChannelCredentialView:
        logger.info(
            f"保存商户凭据 | channel={payload.channel} merchant_no={payload.merchant_no} actor={actor}"
        )
        blob = LlmSecretVault.encrypt_api_key(payload.secrets)
        if not blob:
            raise BusinessException(message="商户密钥不能为空", code="CREDENTIAL_SECRETS_REQUIRED")
        existing = await self.repo.get_by_channel(payload.channel)
        if existing is None:
            row = await self._insert_or_rotate(payload, blob, actor)
        else:
            row = await self._rotate(existing, payload, blob, actor)
        view = self._to_view(payload.channel, row)
        await self.session.commit()
        return view

    async def delete_channel(self, channel: PaymentChannel, actor: str) -> None:
        logger.info(f"删除商户凭据 | channel={channel} actor={actor}")
        if channel not in _CHANNELS:
            raise NotFoundException("收款通道")
        await self.repo.delete_by_channel(channel)
        await self.session.commit()

    async def configured_channels(self) -> set[str]:
        logger.info("查询已配置收款通道")
        return await self.repo.configured_channels()

    async def _insert_or_rotate(
        self, payload: PaymentChannelCredentialPut, blob: str, actor: str,
    ) -> PaymentChannelCredential:
        try:
            row = await self.repo.create(
                channel=payload.channel,
                merchant_no=payload.merchant_no,
                secrets_encrypted=blob,
                key_version=1,
                rotated_at=None,
                created_by=actor,
                updated_by=actor,
            )
            return row
        except IntegrityError:
            await self.session.rollback()
            raced = await self.repo.get_by_channel(payload.channel)
            if raced is None:
                raise
            return await self._rotate(raced, payload, blob, actor)

    async def _rotate(
        self,
        row: PaymentChannelCredential,
        payload: PaymentChannelCredentialPut,
        blob: str,
        actor: str,
    ) -> PaymentChannelCredential:
        row.merchant_no = payload.merchant_no
        row.secrets_encrypted = blob
        row.key_version = int(row.key_version or 1) + 1
        row.rotated_at = _now()
        row.updated_by = actor
        await self.session.flush()
        return row

    @staticmethod
    def _to_view(
        channel: PaymentChannel, row: Optional[PaymentChannelCredential],
    ) -> PaymentChannelCredentialView:
        if row is None:
            return _empty_view(channel)
        return PaymentChannelCredentialView(
            channel=channel,
            configured=True,
            merchant_no=str(row.merchant_no),
            secrets_masked=SECRETS_MASK,
            key_version=int(row.key_version or 1),
            rotated_at=row.rotated_at,
            created_by=row.created_by,
            updated_by=row.updated_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
