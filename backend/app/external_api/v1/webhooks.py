"""外部 API - Webhook 接收端点

职责：
- 接收爬虫进程的回调通知（任务终态推进：completed/failed）
- HMAC-SHA256 签名验证（密钥见 config/default/webhook.yml，与 Scrapy 侧共享）
- 时间戳防重放（允许最大时钟偏移由 WEBHOOK.MAX_CLOCK_SKEW 控制）

签名算法（与 scrapy/extensions 的 SpiderCloseWebhook 保持一致）：
    signature = HMAC-SHA256(secret, f"{timestamp}.{raw_body}") 的 hex
请求头：
    X-Webhook-Timestamp: Unix 秒级时间戳
    X-Webhook-Signature:  签名 hex
"""
import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.spider_service import SpiderService
from config import settings
from platform_core.db import get_async_db
from platform_core.logger import get_logger

router = APIRouter()


def verify_webhook_signature(
    raw_body: bytes, timestamp: str, signature: str
) -> bool:
    """校验 Webhook 签名：HMAC-SHA256(secret, "{timestamp}.{raw_body}")

    返回 False 的情形：缺头、时间戳非法/超窗、签名不匹配。
    """
    if not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    max_skew = settings.get("WEBHOOK.MAX_CLOCK_SKEW", 300)
    if abs(time.time() - ts) > max_skew:
        return False
    secret = str(settings.WEBHOOK.SECRET_KEY)
    payload = f"{timestamp}.".encode() + raw_body
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/spider/callback")
async def spider_callback(
    request: Request,
    x_webhook_timestamp: str = Header(None, alias="X-Webhook-Timestamp"),
    x_webhook_signature: str = Header(None, alias="X-Webhook-Signature"),
    session: AsyncSession = Depends(get_async_db),
):
    """接收爬虫任务完成的回调（签名验证 → 任务终态推进）"""
    logger = get_logger("api")
    raw_body = await request.body()

    if not verify_webhook_signature(raw_body, x_webhook_timestamp, x_webhook_signature):
        logger.warning("爬虫回调签名校验失败，已拒绝")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        body = json.loads(raw_body)
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    task_id = body.get("task_id")
    status = body.get("status")
    logger.info(f"收到爬虫回调: task_id={task_id}, status={status}")

    if not isinstance(task_id, int) or status not in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="task_id 必须为整数，status 必须为 completed/failed")

    service = SpiderService(session)
    item_count = body.get("item_count")
    task = await service.finish_task(
        task_id=task_id,
        status=status,
        error_message=body.get("error_message"),
        item_count=item_count if isinstance(item_count, int) else None,
    )
    return {
        "status": "received",
        "task_id": task.id,
        "task_status": task.status,
        "result_count": task.result_count,
        "timestamp": int(time.time()),
    }


def validate_api_key(api_key: str) -> bool:
    """校验第三方调用方 API Key（外部 API 统一鉴权入口，公开查询端点共用）

    密钥来源（.env 可覆盖）：
    - EXTERNAL_API.API_KEYS 列表（新口径，config/default/external_api.yml，
      AUTO_AGENTS_EXTERNAL_API__API_KEYS='["key1"]'）
    - EXTERNAL_API.API_KEY 单 key（旧口径，过渡期兼容，见 config/default/api.yml
      的 deprecated 注记）
    两处配置合并比对；均未配置（空）时一律拒绝，杜绝默认密钥。
    """
    valid_keys = _configured_api_keys()
    if not valid_keys:
        return False
    # 以 bytes 比较：避免非 ASCII 输入触发 compare_digest 的 TypeError
    candidate = api_key.encode("utf-8")
    return any(hmac.compare_digest(candidate, key.encode("utf-8")) for key in valid_keys)


def _configured_api_keys() -> list[str]:
    """读取全部有效密钥（新列表 API_KEYS + 旧单 key API_KEY 过渡期兼容合并）

    - API_KEYS 兼容环境变量字符串注入的容错解析
    - 旧单 key 非空时并入有效列表（去重）；迁移至 API_KEYS 后可移除该兼容分支
    """
    keys = settings.get("EXTERNAL_API.API_KEYS", []) or []
    if isinstance(keys, str):
        try:
            parsed = json.loads(keys)
        except ValueError:
            parsed = keys
        keys = parsed if isinstance(parsed, list) else [parsed]
    valid = [str(k) for k in keys if str(k).strip()]
    # 过渡期兼容：旧单 key 配置（config/default/api.yml，deprecated）
    legacy = str(settings.get("EXTERNAL_API.API_KEY", "") or "").strip()
    if legacy and legacy not in valid:
        valid.append(legacy)
    return valid

