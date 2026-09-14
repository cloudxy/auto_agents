"""C5 租户交付 webhook：签名头 + 成功投递。"""
import httpx
import pytest

from backend.services.delivery_webhook_service import DeliveryWebhookService


@pytest.mark.asyncio
async def test_deliver_includes_hmac_and_succeeds():
    async def ok_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-webhook-signature")
        assert request.headers.get("x-webhook-timestamp")
        assert len(request.headers["x-webhook-signature"]) == 64
        return httpx.Response(200)

    ok = await DeliveryWebhookService().deliver(
        "http://127.0.0.1/hook",
        {"task_id": 7, "event": "task.finished"},
        secret="abc",
        transport=httpx.MockTransport(ok_handler),
    )
    assert ok is True
