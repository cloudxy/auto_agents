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

from backend.config_consts import EXTERNAL_API_KEY_BINDINGS
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
    """校验第三方调用方 API Key（状态/统计等公开端点）

    密钥来源（.env 可覆盖）：
    - EXTERNAL_API.API_KEYS 列表（config/default/external_api.yml，
      AUTO_AGENTS_EXTERNAL_API__API_KEYS='["key1"]'）
    - EXTERNAL_API.API_KEY 单 key（旧口径，过渡期兼容，见 config/default/api.yml
      的 deprecated 注记）
    两处配置合并比对；均未配置（空）时一律拒绝，杜绝默认密钥。
    出站拉数不走本函数：须 bound_tenant_id（KEY_BINDINGS 恰好一租户）。
    """
    valid_keys = _configured_api_keys()
    if not valid_keys:
        return False
    # 以 bytes 比较：避免非 ASCII 输入触发 compare_digest 的 TypeError
    candidate = api_key.encode("utf-8")
    return any(hmac.compare_digest(candidate, key.encode("utf-8")) for key in valid_keys)


def bound_tenant_id(api_key: str) -> int | None:
    """出站拉数：钥匙绑到恰好一个 tenant_id 才放行。

    只认 EXTERNAL_API.KEY_BINDINGS。旧字符串列表 / 旧单 key 无企业维，
    视为未绑定（GWT-13.4）；同一钥匙映到两个租户亦未绑定。
    """
    if not api_key or not str(api_key).strip():
        return None
    candidate = api_key.encode("utf-8")
    matched: int | None = None
    for key, tenant_id in _configured_key_bindings().items():
        if not hmac.compare_digest(candidate, key.encode("utf-8")):
            continue
        if matched is not None and matched != tenant_id:
            return None
        matched = tenant_id
    return matched


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


def _configured_key_bindings() -> dict[str, int]:
    """读取 key→tenant_id（恰好一租户；冲突钥匙丢弃）。"""
    raw = settings.get("EXTERNAL_API.KEY_BINDINGS", EXTERNAL_API_KEY_BINDINGS) or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = []
    return _exactly_one_tenant(_binding_pairs(raw))


def _binding_pairs(raw) -> list[tuple[str, int]]:
    """把配置展开成 (key, tenant_id)；字符串列表项丢弃（未绑定）。"""
    pairs: list[tuple[str, int]] = []
    if isinstance(raw, dict):
        for key, value in raw.items():
            tid = _as_tenant_id(value)
            if str(key).strip() and tid is not None:
                pairs.append((str(key), tid))
        return pairs
    if not isinstance(raw, list):
        return pairs
    for item in raw:
        parsed = _binding_item(item)
        if parsed is not None:
            pairs.append(parsed)
    return pairs


def _binding_item(item) -> tuple[str, int] | None:
    if not isinstance(item, dict):
        return None
    key = str(item.get("key", "") or "").strip()
    tid = _as_tenant_id(item.get("tenant_id"))
    if not key or tid is None:
        return None
    return key, tid


def _as_tenant_id(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        n = int(value.strip())
        return n if n > 0 else None
    return None


def _exactly_one_tenant(pairs: list[tuple[str, int]]) -> dict[str, int]:
    assigned: dict[str, int] = {}
    conflicts: set[str] = set()
    for key, tid in pairs:
        if key in conflicts:
            continue
        prev = assigned.get(key)
        if prev is None:
            assigned[key] = tid
        elif prev != tid:
            conflicts.add(key)
            del assigned[key]
    return assigned

