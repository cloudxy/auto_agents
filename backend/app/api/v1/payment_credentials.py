"""超管商户凭据：仅 require_platform_admin_or_404；读回掩码。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, require_platform_admin_or_404
from backend.app.responses import deleted, ok
from backend.services.payment_credential_service import PaymentCredentialService
from platform_core.db import get_async_db
from platform_core.logger import get_logger
from platform_core.schemas.payment_channel_credential import (
    PaymentChannel,
    PaymentChannelCredentialPut,
)

logger = get_logger("api.payment_credentials")

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_async_db)) -> PaymentCredentialService:
    return PaymentCredentialService(session)


@router.get("")
async def list_payment_credentials(
    user: CurrentUser = Depends(require_platform_admin_or_404),
    service: PaymentCredentialService = Depends(_svc),
):
    logger.info(f"超管读取商户凭据 | user={user.username}")
    data = await service.list_for_admin()
    return ok(data=data.model_dump(mode="json"))


@router.put("")
async def put_payment_credential(
    payload: PaymentChannelCredentialPut,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
    service: PaymentCredentialService = Depends(_svc),
):
    logger.info(f"超管保存商户凭据 | user={user.username} channel={payload.channel}")
    view = await service.put(payload, actor=user.username)
    await record_audit(
        session, user, "payment_credential.put", payload.channel,
        detail={"channel": payload.channel, "key_version": view.key_version},
    )
    return ok(data=view.model_dump(mode="json"))


@router.delete("/{channel}")
async def delete_payment_credential(
    channel: PaymentChannel,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
    service: PaymentCredentialService = Depends(_svc),
):
    logger.info(f"超管删除商户凭据 | user={user.username} channel={channel}")
    await service.delete_channel(channel, actor=user.username)
    await record_audit(session, user, "payment_credential.delete", channel)
    return deleted(data={"channel": channel, "configured": False})
