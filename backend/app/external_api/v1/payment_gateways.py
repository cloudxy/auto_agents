"""支付宝 / 微信支付真实异步通知（RSA2 / APIv3 AEAD 验签，非 HMAC 夹具）。

与 `/api/v1/billing/notify/{channel}`（本仓库自定义 HMAC 四要素通知，沙箱/CI
用，见 `payment_notify_service.handle`）平行存在、互不替代：本文件验真通道
自己的原生签名协议，验真通过后调用
`PaymentNotifyService.handle_verified_fields` 复用同一套订单四要素核对 +
CAS 状态机，避免真实网关接入把状态转移逻辑重写一遍带出新缺陷。

两个通道对响应格式的官方要求不同，都不套用本仓库统一的 `ok()`/`ApiResponse`
信封：
- 支付宝要求响应体是纯文本 `"success"`；不回复该文本会被判定未收到，按其
  重试策略重发（最多 24 小时内多次）。
- 微信支付 v3 要求 `{"code": "SUCCESS", "message": "成功"}` 且 HTTP 200；
  非 200 状态码同样会触发重试。

验真失败（签名不对/四要素不符/找不到订单）时两边都仍回复"收到"（success /
200 SUCCESS），不开通、不落 payment_succeeded——避免因为一次可疑请求就被
对方判定端点异常触发重试风暴；真正的处理结果只由 `handle_verified_fields`
内部的日志与订单状态体现。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.payment_channel_credential_repository import (
    PaymentChannelCredentialRepository,
)
from backend.services.llm_secret_vault import LlmSecretVault
from backend.services.payment_gateways.alipay_gateway import AlipayGateway
from backend.services.payment_gateways.secrets_schema import (
    parse_alipay_secrets,
    parse_wechat_secrets,
)
from backend.services.payment_gateways.wechat_gateway import WechatGateway
from backend.services.payment_notify_service import PaymentNotifyService
from platform_core.db import get_async_db
from platform_core.logger import get_logger

logger = get_logger("external.payment_gateways")

router = APIRouter()

_ALIPAY_SUCCESS_STATUSES = frozenset({"TRADE_SUCCESS", "TRADE_FINISHED"})
_ALIPAY_FAIL_STATUSES = frozenset({"TRADE_CLOSED"})


async def _configured_secrets(session: AsyncSession, channel: str):
    repo = PaymentChannelCredentialRepository(session)
    row = await repo.get_by_channel(channel)
    if row is None:
        return None, None
    plain = LlmSecretVault.decrypt_api_key(str(row.secrets_encrypted or ""))
    if not plain:
        return None, None
    return plain, str(row.merchant_no or "")


@router.post("/alipay/notify")
async def alipay_notify(
    request: Request, session: AsyncSession = Depends(get_async_db),
) -> Response:
    """支付宝异步通知：form 编码，字段名见官方文档（out_trade_no/trade_status/
    total_amount/seller_id/trade_no）。响应体必须是纯文本 "success"。"""
    form = dict((await request.form()).items())
    order_no = str(form.get("out_trade_no") or "")
    logger.info(f"alipay.notify 收到 | out_trade_no={order_no}")
    plain, _merchant_hint = await _configured_secrets(session, "alipay")
    if not plain or not order_no:
        return Response(content="success", media_type="text/plain")
    try:
        secrets = parse_alipay_secrets(plain)
    except Exception as exc:  # noqa: BLE001 — 密钥包格式异常不应让通知端点炸 500
        logger.warning(f"alipay.notify 商户密钥解析失败 | err={exc}")
        return Response(content="success", media_type="text/plain")
    from config import settings

    sandbox = bool(settings.get("PAYMENT.ALIPAY.SANDBOX", False))
    gateway_url = str(settings.get(
        "PAYMENT.ALIPAY.SANDBOX_GATEWAY" if sandbox else "PAYMENT.ALIPAY.GATEWAY", "",
    ))
    gw = AlipayGateway(secrets, gateway_url=gateway_url)
    if not gw.verify_notify(form):
        logger.warning(f"alipay.notify 验签失败 | out_trade_no={order_no}")
        return Response(content="success", media_type="text/plain")
    trade_status = str(form.get("trade_status") or "")
    if trade_status in _ALIPAY_SUCCESS_STATUSES:
        mapped_status = "success"
    elif trade_status in _ALIPAY_FAIL_STATUSES:
        mapped_status = "cancel"
    else:
        logger.info(f"alipay.notify 非闭集状态，忽略 | trade_status={trade_status}")
        return Response(content="success", media_type="text/plain")
    yuan = str(form.get("total_amount") or "0")
    try:
        amount_cents = int(round(float(yuan) * 100))
    except ValueError:
        amount_cents = 0
    notify_svc = PaymentNotifyService(session)
    await notify_svc.handle_verified_fields(
        "alipay",
        order_no=order_no, merchant_no=str(form.get("seller_id") or ""),
        amount_cents=amount_cents, trade_status=mapped_status,
        channel_trade_no=str(form.get("trade_no") or "") or None,
    )
    return Response(content="success", media_type="text/plain")


@router.post("/wechat/notify")
async def wechat_notify(
    request: Request, session: AsyncSession = Depends(get_async_db),
) -> Response:
    """微信支付 v3 异步通知：JSON body + Wechatpay-* 签名头，resource 字段
    AEAD 加密。响应必须是 {"code":"SUCCESS","message":"成功"} 且 HTTP 200。
    """
    body = await request.body()
    plain, _merchant_hint = await _configured_secrets(session, "wechat")
    ok_resp = Response(
        content='{"code":"SUCCESS","message":"成功"}',
        media_type="application/json",
    )
    if not plain:
        return ok_resp
    try:
        secrets = parse_wechat_secrets(plain)
    except Exception as exc:  # noqa: BLE001 — 密钥包格式异常不应让通知端点炸 500
        logger.warning(f"wechat.notify 商户密钥解析失败 | err={exc}")
        return ok_resp
    from config import settings

    cert_dir = str(settings.get("PAYMENT.WECHAT.CERT_DIR", "storage/wechat_certs"))
    try:
        gw = WechatGateway(secrets, cert_dir=cert_dir)
    except Exception as exc:  # noqa: BLE001 — 网关初始化异常（证书/网络）不应让通知端点炸 500
        logger.warning(f"wechat.notify 网关初始化失败 | err={exc}")
        return ok_resp
    result = gw.verify_and_decrypt_notify(dict(request.headers), body)
    if not result:
        logger.warning("wechat.notify 验签/解密失败")
        return ok_resp
    resource = result.get("resource") or {}
    order_no = str(resource.get("out_trade_no") or "")
    trade_state = str(resource.get("trade_state") or "")
    amount = resource.get("amount") or {}
    amount_cents = int(amount.get("total") or 0)
    mapped_status = "success" if trade_state == "SUCCESS" else (
        "cancel" if trade_state in ("CLOSED", "REVOKED", "PAYERROR") else ""
    )
    if not order_no or not mapped_status:
        logger.info(f"wechat.notify 非闭集状态，忽略 | trade_state={trade_state}")
        return ok_resp
    notify_svc = PaymentNotifyService(session)
    await notify_svc.handle_verified_fields(
        "wechat",
        order_no=order_no, merchant_no=str(resource.get("mchid") or ""),
        amount_cents=amount_cents, trade_status=mapped_status,
        channel_trade_no=str(resource.get("transaction_id") or "") or None,
    )
    return ok_resp
