"""微信支付 Native（扫码）下单 + 回调验签：包一层 `wechatpayv3`（APIv3）。

选用第三方维护 SDK 而非直接用 alipay_gateway.py 那种手写方案的原因：APIv3
的平台证书自动下载/轮换 + 回调 AEAD_AES_256_GCM 解密是协议里最容易写错、
最需要跟随官方更新的部分，交给持续维护的 SDK 比自己重实现更可靠。

`wechatpayv3` 内部用 `requests`（同步阻塞 I/O），本模块的方法因此是同步的；
调用方（payment_provider.py）在 async 上下文里用 `asyncio.to_thread` 包一层
（项目既有约定：异步优先，同步第三方调用走 to_thread，不在事件循环里硬等）。
"""
from __future__ import annotations

import json
from pathlib import Path

from wechatpayv3 import WeChatPay, WeChatPayType

from backend.services.payment_gateways.secrets_schema import WechatSecrets
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger

logger = get_logger("service.payment.wechat")


class WechatGateway:
    """一次调用绑定一套商户密钥；cert_dir 跨调用复用以缓存平台证书（避免每单都拉证书）。"""

    def __init__(self, secrets: WechatSecrets, *, cert_dir: str, sandbox: bool = False):
        Path(cert_dir).mkdir(parents=True, exist_ok=True)
        try:
            self._client = WeChatPay(
                wechatpay_type=WeChatPayType.NATIVE,
                mchid=secrets.mch_id,
                private_key=secrets.apiclient_key,
                cert_serial_no=secrets.cert_serial_no,
                appid=secrets.appid,
                apiv3_key=secrets.api_v3_key,
                cert_dir=cert_dir,
            )
        except Exception as exc:  # noqa: BLE001 — SDK 初始化异常类型不固定（网络/证书/密钥格式都可能）
            logger.warning(f"微信支付网关初始化失败 | err={exc}")
            raise BusinessException(
                message=f"微信支付商户凭据初始化失败，请核对密钥包字段: {exc}",
                code="PAYMENT_GATEWAY_INIT_FAILED",
            ) from exc
        self._sandbox = sandbox

    def create_native_pay(
        self, *, out_trade_no: str, amount_cents: int, description: str, notify_url: str,
    ) -> str:
        """Native 扫码支付下单，返回 code_url（供前端渲染二维码）。"""
        code, message = self._client.pay(
            description=description,
            out_trade_no=out_trade_no,
            amount={"total": int(amount_cents), "currency": "CNY"},
            notify_url=notify_url,
            pay_type=WeChatPayType.NATIVE,
        )
        try:
            body = json.loads(message) if message else {}
        except (TypeError, ValueError):
            body = {}
        if code not in (200, 204) or "code_url" not in body:
            err = body.get("message") or message
            logger.warning(f"微信支付下单失败 | code={code} err={err}")
            raise BusinessException(
                message=f"微信支付下单失败: {err}", code="PAYMENT_GATEWAY_CREATE_FAILED",
            )
        logger.info(f"wechat.native_pay 下单成功 | out_trade_no={out_trade_no}")
        return str(body["code_url"])

    def verify_and_decrypt_notify(self, headers: dict, body: bytes | str) -> dict | None:
        """验签 + 解密官方异步通知；签名不对/无法解密返回 None（不抛异常，由调用方 200 吞掉）。"""
        try:
            result = self._client.callback(headers=headers, body=body)
        except Exception as exc:  # noqa: BLE001 — SDK 对畸形回调体的异常类型不固定
            logger.warning(f"微信支付回调解析异常 | err={exc}")
            return None
        return result
