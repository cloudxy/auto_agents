"""租户数据交付 webhook（roadmap C5）：任务终态签名 POST + 退避重试。"""
import asyncio
import hashlib
import hmac
import json
import time
from typing import Optional

import httpx

from config import settings
from platform_core.logger import get_logger

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
        key = (secret or str(settings.get("WEBHOOK.SECRET_KEY", "") or "")).encode()
        body = json.dumps(payload, ensure_ascii=False)
        for attempt in range(_MAX_ATTEMPTS):
            ts = str(int(time.time()))
            sig = hmac.new(key, f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
            try:
                kwargs: dict = {"trust_env": False, "timeout": 10}
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
                if resp.status_code < 400:
                    logger.info(f"租户交付成功 | task={payload.get('task_id')} http={resp.status_code}")
                    return True
                logger.warning(
                    f"租户交付 HTTP {resp.status_code} attempt={attempt + 1}"
                )
            except Exception as e:  # noqa: BLE001 交付失败不影响终态
                logger.warning(f"租户交付失败 attempt={attempt + 1}: {e}")
            await asyncio.sleep(min(8, 2 ** attempt))
        return False
