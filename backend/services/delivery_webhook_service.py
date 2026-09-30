"""租户数据交付 webhook（roadmap C5）：任务终态签名 POST + 退避重试。

SSRF（审计 BUG-22 / P0-8）：每次发送前经 outbound_guard 复检（设置时校验过的域名
事后可能改解析到内网），不跟随重定向；被拒直接放弃，不重试。
签名密钥：调用方传租户独立密钥；缺省回退平台 WEBHOOK.SECRET_KEY（仅兼容旧数据）。
"""
import asyncio
import hashlib
import hmac
import json
import time
from typing import Optional

import httpx

from config import settings
from platform_core.logger import get_logger
from platform_core.outbound_guard import OutboundBlocked, assert_public_url

logger = get_logger("service.delivery_webhook")

_MAX_ATTEMPTS = 3


class DeliveryWebhookService:
    async def deliver(
        self,
        url: str,
        payload: dict,
        secret: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> bool:
        logger.info(f"租户交付 webhook | url={url[:48]} task={payload.get('task_id')}")
        if not url:
            return False
        try:
            await assert_public_url(url)
        except OutboundBlocked as exc:
            logger.warning(f"租户交付地址被出站守卫拒绝，放弃投递 | task={payload.get('task_id')} reason={exc.message}")
            return False
        key = (secret or str(settings.get("WEBHOOK.SECRET_KEY", "") or "")).encode()
        body = json.dumps(payload, ensure_ascii=False)
        for attempt in range(_MAX_ATTEMPTS):
            ts = str(int(time.time()))
            sig = hmac.new(key, f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
            try:
                kwargs: dict = {"trust_env": False, "timeout": 10, "follow_redirects": False}
                if transport is not None:
                    kwargs["transport"] = transport
                async with httpx.AsyncClient(**kwargs) as client:
                    resp = await client.post(
                        url,
                        content=body.encode(),
                        headers={
                            "Content-Type": "application/json",
                            "X-Webhook-Timestamp": ts,
                            "X-Webhook-Signature": sig,
                        },
                    )
                # 只认 2xx：不跟随重定向时 3xx 表示并未投递到目标（审计 P0-8）
                if 200 <= resp.status_code < 300:
                    logger.info(f"租户交付成功 | task={payload.get('task_id')} http={resp.status_code}")
                    return True
                logger.warning(
                    f"租户交付 HTTP {resp.status_code} attempt={attempt + 1}"
                )
            except Exception as e:  # noqa: BLE001 交付失败不影响终态
                logger.warning(f"租户交付失败 attempt={attempt + 1}: {e}")
            await asyncio.sleep(min(8, 2 ** attempt))
        return False
