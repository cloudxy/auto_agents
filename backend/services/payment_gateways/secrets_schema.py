"""商户密钥包 JSON 形状（PaymentChannelCredentialPut.secrets 的负载约定，
仅在真实网关这条通路上生效）。

`payment_channel_credentials.secrets_encrypted` 这个字段是双用的：本仓库
既有的 HMAC 通知夹具通路（payment_notify_service._current_secret）把解密
后的明文当成一个不透明的共享密钥字符串直接喂给 HMAC；本模块给真实支付宝/
微信网关通路定义的是结构化 JSON 形状。**两者不冲突**——`PaymentCredentialService
.put` 不在保存时强制校验 JSON 形状（不破坏既有沙箱/CI 用的 HMAC 密钥字符串
写法），校验只发生在真正调用 `create_payment_intent` 创建在线支付意图时
（懒校验，见 payment_provider.py）。管理后台的结构化表单会在提交前拼好
合法 JSON，超管走 UI 基本不会撞见这里的报错；只有直接调 API 塞坏 JSON 才会。

字段名直接对齐支付宝/微信开放平台文档里的官方术语，方便超管照抄后台申请
页面的原始命名去填，不做额外的改名映射。
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger

logger = get_logger("service.payment.secrets_schema")


@dataclass(frozen=True)
class AlipaySecrets:
    app_id: str
    app_private_key: str  # PEM，商户 RSA2 私钥（PKCS1 或 PKCS8 均可）
    alipay_public_key: str  # PEM，支付宝公钥（"公钥模式"，非证书模式）


@dataclass(frozen=True)
class WechatSecrets:
    mch_id: str
    api_v3_key: str
    apiclient_key: str  # PEM，商户 API 证书私钥（apiclient_key.pem 内容）
    cert_serial_no: str  # 商户 API 证书序列号
    appid: str  # 应用 APPID（Native 支付仍需一个已绑定的 appid）


_ALIPAY_REQUIRED = ("app_id", "app_private_key", "alipay_public_key")
_WECHAT_REQUIRED = ("mch_id", "api_v3_key", "apiclient_key", "cert_serial_no", "appid")


def _parse_json(channel: str, raw: str) -> dict:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise BusinessException(
            message=f"{channel} 密钥包必须是 JSON 对象（超管后台粘贴处），解析失败: {exc}",
            code="PAYMENT_SECRETS_INVALID_JSON",
        ) from exc
    if not isinstance(data, dict):
        raise BusinessException(
            message=f"{channel} 密钥包必须是 JSON 对象，不能是数组/字符串等其他类型",
            code="PAYMENT_SECRETS_INVALID_JSON",
        )
    return data


def _require(channel: str, data: dict, keys: tuple[str, ...]) -> None:
    missing = [k for k in keys if not str(data.get(k) or "").strip()]
    if missing:
        raise BusinessException(
            message=f"{channel} 密钥包缺少字段: {', '.join(missing)}",
            code="PAYMENT_SECRETS_MISSING_FIELD",
        )


def parse_alipay_secrets(raw: str) -> AlipaySecrets:
    logger.debug("解析支付宝密钥包")
    data = _parse_json("支付宝", raw)
    _require("支付宝", data, _ALIPAY_REQUIRED)
    return AlipaySecrets(
        app_id=str(data["app_id"]).strip(),
        app_private_key=str(data["app_private_key"]).strip(),
        alipay_public_key=str(data["alipay_public_key"]).strip(),
    )


def parse_wechat_secrets(raw: str) -> WechatSecrets:
    logger.debug("解析微信支付密钥包")
    data = _parse_json("微信支付", raw)
    _require("微信支付", data, _WECHAT_REQUIRED)
    return WechatSecrets(
        mch_id=str(data["mch_id"]).strip(),
        api_v3_key=str(data["api_v3_key"]).strip(),
        apiclient_key=str(data["apiclient_key"]).strip(),
        cert_serial_no=str(data["cert_serial_no"]).strip(),
        appid=str(data["appid"]).strip(),
    )


def validate_secrets(channel: str, raw: str) -> None:
    """校验密钥包 JSON 形状是否合法（不保证密钥内容本身有效）。"""
    logger.debug(f"校验密钥包形状 | channel={channel}")
    if channel == "alipay":
        parse_alipay_secrets(raw)
    elif channel == "wechat":
        parse_wechat_secrets(raw)
