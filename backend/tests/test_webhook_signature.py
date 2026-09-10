"""Webhook 签名验证单测 - 数据闭环回调安全边界

覆盖：
- 正确签名通过
- 错误签名 / 缺头 / 时间戳超窗被拒绝
- 签名与 Scrapy 侧 SpiderCloseWebhook 的算法一致性（同一函数式算法交叉验证）
"""
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.external_api.v1.webhooks import verify_webhook_signature  # noqa: E402
from config import settings  # noqa: E402


def _sign(secret: str, timestamp: str, body: bytes) -> str:
    """与 scrapy/extensions SpiderCloseWebhook 相同的签名算法（交叉验证用）"""
    payload = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def test_valid_signature_passes():
    body = json.dumps({"task_id": 1, "status": "completed"}).encode()
    ts = str(int(time.time()))
    sig = _sign(str(settings.WEBHOOK.SECRET_KEY), ts, body)
    assert verify_webhook_signature(body, ts, sig) is True


def test_tampered_body_rejected():
    body = json.dumps({"task_id": 1, "status": "completed"}).encode()
    ts = str(int(time.time()))
    sig = _sign(str(settings.WEBHOOK.SECRET_KEY), ts, body)
    tampered = json.dumps({"task_id": 999, "status": "failed"}).encode()
    assert verify_webhook_signature(tampered, ts, sig) is False


def test_missing_headers_rejected():
    body = b"{}"
    assert verify_webhook_signature(body, None, None) is False
    assert verify_webhook_signature(body, "", "deadbeef") is False


def test_expired_timestamp_rejected():
    body = b"{}"
    old_ts = str(int(time.time()) - int(settings.get("WEBHOOK.MAX_CLOCK_SKEW", 300)) - 10)
    sig = _sign(str(settings.WEBHOOK.SECRET_KEY), old_ts, body)
    assert verify_webhook_signature(body, old_ts, sig) is False


def test_invalid_timestamp_rejected():
    assert verify_webhook_signature(b"{}", "not-a-number", "deadbeef") is False


def test_wrong_secret_rejected():
    body = b"{}"
    ts = str(int(time.time()))
    sig = _sign("wrong-secret", ts, body)
    assert verify_webhook_signature(body, ts, sig) is False
